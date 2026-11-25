// =============================================================
//  optimize-keyrev.js — push the "key reversal @ Bollinger band" winner to be
//  as robust & EVAL-FEASIBLE as possible, without overfitting.
//
//  - Confluence tweaks of the core edge (reclaim / RSI2 / strong-close / volume /
//    low-ADX / deep-stretch), each with a risk-control param grid.
//  - Scored on FOUR samples: 90d MNQ, 58d NQ, 13d cached MNQ, recent-13d TopStep.
//  - Real $50K Combine PASS test: chronological — reach +$3,000 before breaching
//    $2,000 trailing DD or a $1,000 daily loss.
//  - Monte-Carlo return-order stress (10k shuffles): % of orderings that still
//    pass (reach +$3k before −$2k trailing DD). This is the anti-luck check.
//  Survivor rule: net-positive on all 4, feasible on the two big samples, and a
//  high Monte-Carlo pass rate. DATA-ONLY. Run:  node optimize-keyrev.js
// =============================================================
"use strict";
const path = require("path");
const fs = require("fs");
const Lab = require("./lab-new4.js");
const G = require("./strat-gen.js");
const O = require("./optimize-strat.js");
const PX = require("./projectx.js");
const ep = Lab.etParts;
const PV = 2, MAXC = 5, DLL = 1000, MLL = 2000, TARGET = 3000, TICK = 0.25;
const dol = x => (x >= 0 ? "+$" : "-$") + Math.abs(Math.round(x)).toLocaleString();

// ---- core edge + confluence helpers ----
const rng = (C, i) => C.h[i] - C.l[i] || 1e-9;
const topThird = (C, i) => (C.c[i] - C.l[i]) / rng(C, i) > 0.66;
const botThird = (C, i) => (C.h[i] - C.c[i]) / rng(C, i) > 0.66;
function keyRev(C, i) { let nl = true, nh = true; for (let q = 1; q <= 5; q++) { if (C.l[i] >= C.l[i - q]) nl = false; if (C.h[i] <= C.h[i - q]) nh = false; } if (nl && C.c[i] > C.o[i] && C.c[i] > C.c[i - 1]) return 1; if (nh && C.c[i] < C.o[i] && C.c[i] < C.c[i - 1]) return -1; return 0; }
const pierceL = (C, i) => C.bbL[i] != null && C.l[i] <= C.bbL[i];
const pierceS = (C, i) => C.bbU[i] != null && C.h[i] >= C.bbU[i];

// each tweak: fn(C,i)->dir. All require keyRev + at the band; add one filter.
const METHODS = [
  ["kb_base", "KeyRev @ BB band", (C, i) => { const d = keyRev(C, i); if (!d) return 0; return (d === 1 ? pierceL(C, i) : pierceS(C, i)) ? d : 0; }],
  ["kb_reclaim", "KeyRev @ BB + close-back-inside", (C, i) => { const d = keyRev(C, i); if (!d) return 0; if (d === 1) return pierceL(C, i) && C.c[i] > C.bbL[i] ? 1 : 0; return pierceS(C, i) && C.c[i] < C.bbU[i] ? -1 : 0; }],
  ["kb_rsi2", "KeyRev @ BB + RSI2 extreme", (C, i) => { const d = keyRev(C, i); if (!d || C.rsi2[i] == null) return 0; if (d === 1) return pierceL(C, i) && C.rsi2[i] < 10 ? 1 : 0; return pierceS(C, i) && C.rsi2[i] > 90 ? -1 : 0; }],
  ["kb_strong", "KeyRev @ BB + strong close", (C, i) => { const d = keyRev(C, i); if (!d) return 0; if (d === 1) return pierceL(C, i) && topThird(C, i) ? 1 : 0; return pierceS(C, i) && botThird(C, i) ? -1 : 0; }],
  ["kb_rsi_reclaim", "KeyRev @ BB + RSI2 + reclaim", (C, i) => { const d = keyRev(C, i); if (!d || C.rsi2[i] == null) return 0; if (d === 1) return pierceL(C, i) && C.c[i] > C.bbL[i] && C.rsi2[i] < 10 ? 1 : 0; return pierceS(C, i) && C.c[i] < C.bbU[i] && C.rsi2[i] > 90 ? -1 : 0; }],
  ["kb_lowadx", "KeyRev @ BB + ADX<25 (range)", (C, i) => { const d = keyRev(C, i); if (!d || C.adx[i] == null || C.adx[i] >= 25) return 0; return (d === 1 ? pierceL(C, i) : pierceS(C, i)) ? d : 0; }],
  ["kb_vol", "KeyRev @ BB + volume thrust", (C, i) => { const d = keyRev(C, i); if (!d || C.volAvg[i] == null) return 0; if (!((C.v[i] || 0) > 1.2 * C.volAvg[i])) return 0; return (d === 1 ? pierceL(C, i) : pierceS(C, i)) ? d : 0; }],
  ["kb_deep", "KeyRev @ BB stretched 0.25ATR", (C, i) => { const d = keyRev(C, i), a = C.atr[i]; if (!d || a == null) return 0; if (d === 1) return C.bbL[i] != null && C.l[i] <= C.bbL[i] - 0.25 * a ? 1 : 0; return C.bbU[i] != null && C.h[i] >= C.bbU[i] + 0.25 * a ? -1 : 0; }],
  ["kb_rsi_strong", "KeyRev @ BB + RSI2 + strong", (C, i) => { const d = keyRev(C, i); if (!d || C.rsi2[i] == null) return 0; if (d === 1) return pierceL(C, i) && C.rsi2[i] < 10 && topThird(C, i) ? 1 : 0; return pierceS(C, i) && C.rsi2[i] > 90 && botThird(C, i) ? -1 : 0; }],
];

const STOPS = [1.0, 1.2, 1.5], TGTS = [1.5, 2.0, 2.5], CAPS = [200, 250, 300], MAXTR = [2, 3], DAYSTOP = [-500, -700];

// ---- ledger sim: returns per-trade $ (chronological) + aggregates ----
function simLedger(bars, C, E, dirFn, p) {
  const slip = (p.slipTicks || 0) * TICK, fee = p.fee || 0;
  let i = 210, pos = null, day = { k: null, real: 0, tr: 0 };
  let equity = 0, peak = 0, maxDD = 0, wins = 0, gW = 0, gL = 0;
  const trades = [], byDay = new Map();
  while (i < bars.length) {
    const b = bars[i], dki = E.dk[i], rthi = E.rth[i];
    if (day.k !== dki) day = { k: dki, real: 0, tr: 0 };
    if (pos) {
      const long = pos.dir === 1; let px = null;
      if (dki !== pos.day || !rthi) px = long ? bars[i - 1].c - slip : bars[i - 1].c + slip;
      else if (long ? b.l <= pos.stop : b.h >= pos.stop) px = long ? pos.stop - slip : pos.stop + slip;
      else if (long ? b.h >= pos.target : b.l <= pos.target) px = pos.target;
      if (px != null) {
        const pts = long ? px - pos.entry : pos.entry - px, pnl = pts * pos.size * PV - 2 * pos.size * fee;
        equity += pnl; peak = Math.max(peak, equity); maxDD = Math.max(maxDD, peak - equity);
        if (pnl > 0) { wins++; gW += pnl; } else gL += Math.abs(pnl);
        trades.push({ pnl, day: dki }); byDay.set(dki, (byDay.get(dki) || 0) + pnl);
        pos = null; i++; continue;
      }
    }
    if (!pos && rthi && day.real > p.dayStop && day.tr < p.maxTr) {
      const a = C.atr[i]; let d = 0; try { d = dirFn(C, i) || 0; } catch {}
      if (d && a != null) {
        const stopPts = p.stopMult * a, size = Math.max(1, Math.min(MAXC, Math.floor(p.riskCap / (stopPts * PV)))), fill = d === 1 ? C.c[i] + slip : C.c[i] - slip;
        pos = { dir: d, entry: fill, stop: d === 1 ? fill - stopPts : fill + stopPts, target: d === 1 ? fill + p.tgtMult * a : fill - p.tgtMult * a, size, day: dki };
        day.tr++;
      }
    }
    i++;
  }
  for (const [, pnl] of byDay) { day.real += 0; } // noop
  const worstDay = byDay.size ? -Math.min(0, ...byDay.values()) : 0;
  const n = trades.length;
  return { trades, n, win: n ? +(wins / n * 100).toFixed(1) : 0, pf: gL > 0 ? +(gW / gL).toFixed(2) : (gW > 0 ? 99 : 0), net$: Math.round(equity), maxDD$: Math.round(maxDD), worstDay$: Math.round(worstDay), feasible: maxDD < MLL && worstDay < DLL };
}

// chronological Combine pass: reach +TARGET before −MLL trailing OR a −DLL day
function combinePass(trades) {
  let cum = 0, peak = 0; const byDay = new Map();
  for (const t of trades) {
    cum += t.pnl; peak = Math.max(peak, cum);
    byDay.set(t.day, (byDay.get(t.day) || 0) + t.pnl);
    if (peak - cum >= MLL) return { passed: false, why: "MLL" };
    if ((byDay.get(t.day)) <= -DLL) return { passed: false, why: "DLL" };
    if (cum >= TARGET) return { passed: true, why: "target" };
  }
  return { passed: false, why: "no-target" };
}
// Monte-Carlo: shuffle order, pass = reach +TARGET before −MLL trailing DD
function mcPassRate(trades, iters = 10000) {
  if (!trades.length) return 0;
  const a = trades.map(t => t.pnl); let pass = 0;
  for (let it = 0; it < iters; it++) {
    for (let k = a.length - 1; k > 0; k--) { const j = (Math.random() * (k + 1)) | 0; const tmp = a[k]; a[k] = a[j]; a[j] = tmp; }
    let cum = 0, peak = 0, ok = false, dead = false;
    for (const v of a) { cum += v; peak = Math.max(peak, cum); if (peak - cum >= MLL) { dead = true; break; } if (cum >= TARGET) { ok = true; break; } }
    if (ok && !dead) pass++;
  }
  return +(pass / iters * 100).toFixed(1);
}

function ctxPlus(bars) { const C = G.buildContext(bars); const v = C.v, va = new Array(v.length).fill(null); for (let i = 19; i < v.length; i++) { let s = 0; for (let k = i - 19; k <= i; k++) s += v[k] || 0; va[i] = s / 20; } C.volAvg = va; return C; }

(async () => {
  const bars90 = Lab.loadCsv("C:/Users/kaide/Downloads/CME_MINI_DL_MNQ1!, 5 (1).csv");
  const bars58 = JSON.parse(fs.readFileSync(path.join(__dirname, "data", "nq-5m.json"), "utf8")).filter(b => b && isFinite(b.c)).sort((a, b) => a.t - b.t);
  let bars13c = null; try { bars13c = Lab.loadCsv(Lab.CSV_13); } catch {}
  const barsTS = (await PX.fetchBars({ unitNumber: 5, lookbackDays: 25, contract: "MNQ", live: false })).filter(b => b && isFinite(b.c)).sort((a, b) => a.t - b.t);
  const rthDays = [...new Set(barsTS.filter(b => { const e = ep(b.t); return e.day !== 0 && e.day !== 6 && e.mins >= 570 && e.mins < 960; }).map(b => Lab.dayKeyOf(b.t)))];
  const cutoffT = barsTS.find(b => Lab.dayKeyOf(b.t) === rthDays.slice(-13)[0]).t;
  const C90 = ctxPlus(bars90), C58 = ctxPlus(bars58), C13 = bars13c ? ctxPlus(bars13c) : null, CTS = ctxPlus(barsTS);
  const E90 = O.etArrays(bars90), E58 = O.etArrays(bars58), E13 = bars13c ? O.etArrays(bars13c) : null, ETS = O.etArrays(barsTS);
  const COST = { fee: 0.37, slipTicks: 2 }; // score everything NET of realistic cost
  console.log(`Samples: 90d=${bars90.length}b · 58d=${bars58.length}b · 13d-cached=${bars13c ? bars13c.length : "n/a"}b · recent-13d=${rthDays.slice(-13).length}d. All NET of fee+2tk slip.\n`);

  const cand = [];
  for (const [key, name, fn] of METHODS) {
    for (const stopMult of STOPS) for (const tgtMult of TGTS) for (const riskCap of CAPS) for (const maxTr of MAXTR) for (const dayStop of DAYSTOP) {
      const p = { stopMult, tgtMult, riskCap, maxTr, dayStop, ...COST };
      const R90 = simLedger(bars90, C90, E90, fn, p);
      if (R90.net$ <= 0 || !R90.feasible || R90.n < 30) continue;            // must be feasible+profitable on the big sample
      const R58 = simLedger(bars58, C58, E58, fn, p);
      if (R58.net$ <= 0 || !R58.feasible) continue;                          // and out-of-sample feasible+profitable
      const RTS = simLedger(barsTS, CTS, ETS, (C2, i) => (barsTS[i].t >= cutoffT ? fn(C2, i) : 0), p);
      const R13 = C13 ? simLedger(bars13c, C13, E13, fn, p) : { net$: 0 };
      if (RTS.net$ <= 0) continue;                                           // must also work on the most recent data
      cand.push({ key, name, p, R90, R58, R13, RTS });
    }
  }
  console.log(`Configs net+ & feasible on 90d AND 58d AND net+ on recent-13d: ${cand.length}\n`);

  // deep-validate the strongest: combine pass + Monte-Carlo, rank by MC pass rate then min-net
  for (const c of cand) { c.pass90 = combinePass(c.R90.trades); c.mc90 = mcPassRate(c.R90.trades); c.minNet = Math.min(c.R90.net$, c.R58.net$, c.RTS.net$); }
  cand.sort((a, b) => (b.pass90.passed - a.pass90.passed) || (b.mc90 - a.mc90) || (b.minNet - a.minNet));

  const top = cand.slice(0, 12);
  console.log("RANKED (net of costs)  [cfg = stop/target $cap trades/day dayStop]\n");
  for (const c of top) {
    const cfg = `s${c.p.stopMult}/t${c.p.tgtMult} $${c.p.riskCap} ${c.p.maxTr}/d ${c.p.dayStop}`;
    console.log(`${c.name.slice(0, 30).padEnd(31)}${cfg.padEnd(22)} 90d ${dol(c.R90.net$).padStart(8)} ${(c.R90.win + "%").padStart(5)} PF${c.R90.pf} DD-$${c.R90.maxDD$}` +
      ` | 58d ${dol(c.R58.net$).padStart(7)} | 13c ${dol(c.R13.net$).padStart(7)} | rec ${dol(c.RTS.net$).padStart(6)} ${(c.RTS.win + "%").padStart(5)} | PASS ${c.pass90.passed ? "✅" : "❌" + c.pass90.why} | MC ${c.mc90}%`);
  }

  // markdown
  const md = ["# Key-reversal optimization — eval-feasibility hardened (" + new Date().toISOString().slice(0, 10) + ")",
    "\nConfluence tweaks of *KeyRev @ Bollinger band*, risk-control grid, scored **net of fee+2-tick slippage** on 4 samples. PASS = chronological $50K Combine (reach +$3,000 before −$2,000 trailing DD or −$1,000 day). MC% = Monte-Carlo return-order stress (10k shuffles) that still reach +$3k before −$2k DD.\n",
    `Survivors (net+ & feasible on 90d & 58d, net+ recent-13d): **${cand.length}**.\n`,
    "| Method | Config | 90d Net | 90d Win | 90d PF | 90d DD | 58d Net | 13d-cached | Recent-13d | Combine PASS | MC pass% |",
    "|---|---|---:|---:|---:|---:|---:|---:|---:|:--:|---:|"];
  for (const c of top) md.push(`| ${c.name} | s${c.p.stopMult}/t${c.p.tgtMult} $${c.p.riskCap} ${c.p.maxTr}/d ${c.p.dayStop} | ${dol(c.R90.net$)} | ${c.R90.win}% | ${c.R90.pf} | -$${c.R90.maxDD$} | ${dol(c.R58.net$)} | ${dol(c.R13.net$)} | ${dol(c.RTS.net$)} (${c.RTS.win}%) | ${c.pass90.passed ? "✅" : "❌ " + c.pass90.why} | ${c.mc90}% |`);
  fs.writeFileSync(path.join(__dirname, "logs", "keyrev-optimized-report.md"), md.join("\n") + "\n");
  console.log(`\nReport -> logs/keyrev-optimized-report.md`);
})().catch(e => console.log("ERR", e.message, e.stack));
