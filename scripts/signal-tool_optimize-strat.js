// =============================================================
//  optimize-strat.js — optimize the surviving entry edges with REAL risk
//  control, scored on a chronological Combine sim (the thing that actually
//  decides "blows the account").
//
//  The raw strat-gen run found edges (FVG retest, pin, mean-revert) that are
//  net-positive on 3 samples but blow the $2k trailing-DD wall at 5 MNQ and
//  win only ~22% (high-RR/ungated). This grids each edge over:
//     - stop / target ATR multiples            (RR + win-rate)
//     - trend (EMA200) / ADX(>20) entry filter (cut bad trades, raise win%)
//     - vol-based position SIZING w/ risk cap   (bounds per-trade $ risk)
//     - daily-loss stop + max-trades/day brakes (caps the bad day -> caps DD)
//  ...and simulates the $50K Combine chronologically (vol-sized $, trailing DD,
//  worst-day) so feasibility is measured the way TopStep measures it.
//
//  Primary = 90-day MNQ CSV. Top configs re-checked on 13d + 58d (OOS).
//  DATA-ONLY. Run:  node optimize-strat.js
// =============================================================
"use strict";
const fs = require("fs");
const path = require("path");
const Lab = require("./lab-new4.js");
const G = require("./strat-gen.js");
const ep = Lab.etParts;

const PV = 2, MAXC = 5, DLL = 1000, MLL = 2000;
const RTH_START = 570, RTH_END = 960;
const CSV_90 = process.argv[2] || "C:\\Users\\kaide\\Downloads\\CME_MINI_DL_MNQ1!, 5 (1).csv";
const OUT_MD = path.join(__dirname, "logs", "optimize-strat-report.md");
const dol = x => (x >= 0 ? "+$" : "-$") + Math.abs(Math.round(x)).toLocaleString();
const inRTH = t => { const e = ep(t); return e.day !== 0 && e.day !== 6 && e.mins >= RTH_START && e.mins < RTH_END; };

// base edges to optimize (the strat-gen survivors worth deepening)
const BASE_KEYS = ["fvg_w6_g02", "fvg_w6_g04", "fvg_w8_g03", "fvg_trend", "pin_2x", "pin_ema50", "zscore_2", "cci_zero", "vwap_2sig", "sweep_swing3", "key_rev"];
const baseMap = new Map(G.ENTRIES.map(([k, name, cat, fn]) => [k, { name, cat, fn }]));

// ---- grid ----
const STOPS = [0.7, 1.0, 1.5];
const TGTS = [1.5, 2.5, 3.5];
const FILTERS = ["none", "trend", "adx", "both"];
const RISKCAPS = [200, 300];
const MAXTRS = [2, 3];
const DAYSTOP = -500;

function withFilter(fn, kind) {
  return (C, i) => {
    let d = fn(C, i) || 0; if (!d) return 0;
    if (kind === "trend" || kind === "both") { if (C.ema200[i] == null) return 0; if (d === 1 && !(C.c[i] > C.ema200[i])) return 0; if (d === -1 && !(C.c[i] < C.ema200[i])) return 0; }
    if (kind === "adx" || kind === "both") { if (C.adx[i] == null || C.adx[i] <= 20) return 0; }
    return d;
  };
}

// precompute per-bar ET fields once (avoids 30M+ Date constructions in the grid)
function etArrays(bars) {
  const dk = new Array(bars.length), rth = new Array(bars.length);
  for (let i = 0; i < bars.length; i++) { const e = ep(bars[i].t); dk[i] = e.k; rth[i] = e.day !== 0 && e.day !== 6 && e.mins >= RTH_START && e.mins < RTH_END; }
  return { dk, rth };
}
// chronological $50K Combine sim with vol sizing + daily brakes.
// cost = { fee, slipTicks }: fee = $/contract/side; slipTicks = adverse ticks on
// market entry & stop fills (target is a resting limit -> no slippage). Defaults
// to frictionless so the grid above is unchanged.
const TICK = 0.25;
function simCombine(bars, C, E, dirFn, p, cost = { fee: 0, slipTicks: 0 }) {
  const slip = (cost.slipTicks || 0) * TICK, fee = cost.fee || 0;
  let i = 210, pos = null, day = { k: null, real: 0, tr: 0 };
  let equity = 0, peak = 0, maxDD = 0, wins = 0, gW = 0, gL = 0, n = 0, fees = 0;
  const byDay = new Map();
  while (i < bars.length) {
    const b = bars[i], dki = E.dk[i], rthi = E.rth[i];
    if (day.k !== dki) day = { k: dki, real: 0, tr: 0 };
    if (pos) {
      const isLong = pos.dir === 1; let px = null;
      if (dki !== pos.day || !rthi) px = (isLong ? bars[i - 1].c - slip : bars[i - 1].c + slip);     // EOD market
      else if (isLong ? b.l <= pos.stop : b.h >= pos.stop) px = (isLong ? pos.stop - slip : pos.stop + slip); // stop market (adverse)
      else if (isLong ? b.h >= pos.target : b.l <= pos.target) px = pos.target;                       // target limit (exact)
      if (px != null) {
        const pts = isLong ? px - pos.entry : pos.entry - px;
        const fee$ = 2 * pos.size * fee;                  // round-trip commissions
        const pnl = pts * pos.size * PV - fee$;
        fees += fee$;
        equity += pnl; peak = Math.max(peak, equity); maxDD = Math.max(maxDD, peak - equity);
        day.real += pnl; byDay.set(dki, (byDay.get(dki) || 0) + pnl);
        if (pnl > 0) { wins++; gW += pnl; } else gL += Math.abs(pnl);
        n++; pos = null; i++; continue;
      }
    }
    if (!pos && rthi && day.real > p.dayStop && day.tr < p.maxTr) {
      const a = C.atr[i]; let d = 0; try { d = dirFn(C, i) || 0; } catch {}
      if (d && a != null) {
        const stopPts = p.stopMult * a, tgtPts = p.tgtMult * a;
        const size = Math.max(1, Math.min(MAXC, Math.floor(p.riskCap / (stopPts * PV))));
        const fill = d === 1 ? C.c[i] + slip : C.c[i] - slip;   // market entry (adverse)
        pos = { dir: d, entry: fill, stop: d === 1 ? fill - stopPts : fill + stopPts, target: d === 1 ? fill + tgtPts : fill - tgtPts, size, day: dki };
        day.tr++;
      }
    }
    i++;
  }
  const worstDay = byDay.size ? -Math.min(0, ...byDay.values()) : 0;
  return { n, win: n ? +(wins / n * 100).toFixed(1) : 0, pf: gL > 0 ? +(gW / gL).toFixed(2) : (gW > 0 ? 99 : 0), net$: Math.round(equity), fees$: Math.round(fees), maxDD$: Math.round(maxDD), worstDay$: Math.round(worstDay), feasible: maxDD < MLL && worstDay < DLL };
}

function loadJson(p) { return JSON.parse(fs.readFileSync(p, "utf8")).filter(b => b && isFinite(b.c)).sort((a, b) => a.t - b.t); }
function span(bars) { return [bars[0].t, bars[bars.length - 1].t].map(s => new Date(s * 1000).toISOString().slice(0, 10)); }

function main() {
  const bars90 = Lab.loadCsv(CSV_90);
  const bars58 = loadJson(path.join(__dirname, "data", "nq-5m.json"));
  let bars13 = null; try { bars13 = Lab.loadCsv(Lab.CSV_13); } catch {}
  const C90 = G.buildContext(bars90), C58 = G.buildContext(bars58), C13 = bars13 ? G.buildContext(bars13) : null;
  const E90 = etArrays(bars90), E58 = etArrays(bars58), E13 = bars13 ? etArrays(bars13) : null;
  const d90 = new Set(bars90.map(b => Lab.dayKeyOf(b.t))).size;
  console.log(`90d primary: ${bars90.length} bars, ${d90} days, ${span(bars90).join(" -> ")}`);

  // precompute filtered dir-fns once per (entry,filter); grid exit/risk on top
  const configs = [];
  for (const key of BASE_KEYS) {
    const base = baseMap.get(key); if (!base) continue;
    for (const filt of FILTERS) {
      const dirFn = withFilter(base.fn, filt);
      for (const stopMult of STOPS) for (const tgtMult of TGTS) for (const riskCap of RISKCAPS) for (const maxTr of MAXTRS) {
        configs.push({ key, name: base.name, cat: base.cat, filt, p: { stopMult, tgtMult, riskCap, maxTr, dayStop: DAYSTOP }, dirFn });
      }
    }
  }
  console.log(`Optimizing ${configs.length} configs (${BASE_KEYS.length} edges × ${FILTERS.length} filters × ${STOPS.length}×${TGTS.length} exits × ${RISKCAPS.length}×${MAXTRS.length} risk)\n`);

  const res = configs.map(cf => ({ ...cf, R: simCombine(bars90, C90, E90, cf.dirFn, cf.p) }));
  // keep feasible + net-positive + enough trades, rank by net$ (then PF)
  const ok = res.filter(r => r.R.feasible && r.R.net$ > 0 && r.R.n >= 20).sort((a, b) => b.R.net$ - a.R.net$ || b.R.pf - a.R.pf);
  console.log(`Feasible @ ≤5 MNQ + net+ + ≥20 trades: ${ok.length} of ${res.length}\n`);

  // confirm top 15 on 13d + 58d (out-of-sample)
  const top = ok.slice(0, 15).map(r => ({ ...r, A58: simCombine(bars58, C58, E58, r.dirFn, r.p), A13: C13 ? simCombine(bars13, C13, E13, r.dirFn, r.p) : null }));

  const lbl = r => `${r.name} [${r.filt}] s${r.p.stopMult}/t${r.p.tgtMult} cap$${r.p.riskCap} ${r.p.maxTr}t/d`;
  console.log("BEST FEASIBLE CONFIGS ON 90d (cross-checked 58d/13d):\n");
  console.log("net90".padStart(9) + " win  PF   DD90".padEnd(20) + " wDay   | 58dNet  58dDD  | 13dNet".padEnd(10));
  for (const r of top) {
    console.log(dol(r.R.net$).padStart(9) + " " + (r.R.win + "%").padStart(5) + " " + String(r.R.pf).padStart(4) + " -$" + String(r.R.maxDD$).padEnd(6) +
      " -$" + String(r.R.worstDay$).padEnd(5) + " | " + dol(r.A58.net$).padStart(8) + " -$" + String(r.A58.maxDD$).padEnd(6) + " | " + (r.A13 ? dol(r.A13.net$).padStart(8) : "n/a") + "  " + lbl(r));
  }

  // markdown
  const md = [];
  md.push(`# Optimized strategies — risk-controlled, 90-day primary (${new Date().toISOString().slice(0, 10)})`);
  md.push(`\nEach surviving edge re-tested with **vol-based sizing (risk cap), daily-loss stop ($${-DAYSTOP}), max-trades/day, and trend/ADX filters**, scored on a **chronological $50K Combine sim** over the **${d90}-day MNQ chart** (${span(bars90).join(" → ")}). "Feasible" = max trailing DD < $${MLL} AND worst day < $${DLL} at the realized vol-based size (≤${MAXC} MNQ). 58d + 13d columns are out-of-sample confirmation. Gross of fees/slippage.`);
  md.push(`\n- Configs tested: **${res.length}**  ·  feasible + net-positive (≥20 trades) on 90d: **${ok.length}**.`);
  md.push(`\n## Best feasible configs (ranked by 90d net)\n`);
  md.push(`| 90d Net | Win% | PF | 90d MaxDD | 90d WorstDay | 58d Net | 58d DD | 58d Feas | 13d Net | Config |`);
  md.push(`|------:|--:|--:|------:|------:|------:|------:|:--:|------:|--------|`);
  for (const r of top) md.push(`| ${dol(r.R.net$)} | ${r.R.win} | ${r.R.pf} | -$${r.R.maxDD$} | -$${r.R.worstDay$} | ${dol(r.A58.net$)} | -$${r.A58.maxDD$} | ${r.A58.feasible ? "yes" : "DD!"} | ${r.A13 ? dol(r.A13.net$) : "n/a"} | ${lbl(r)} |`);
  fs.mkdirSync(path.dirname(OUT_MD), { recursive: true });
  fs.writeFileSync(OUT_MD, md.join("\n") + "\n");
  console.log(`\nReport -> ${OUT_MD}`);
}

module.exports = { simCombine, etArrays, withFilter, baseMap, inRTH, RTH_START, RTH_END };
if (require.main === module) main();
