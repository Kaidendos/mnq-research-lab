// =============================================================
//  backtest-sweep.js — run EVERY stop variant of mean-rev v1.1 over one or
//  more historical windows, scaled to whatever contract size you ask for.
//  Entry, target (=the mean), direction, and all filters are identical
//  across variants — ONLY the stop distance changes, so this is a clean
//  apples-to-apples comparison of stop policy.
//
//  Stop distance per variant = min(mult * ATR(14), cap_pts).
//    baseline (v1.1) : 1.00*ATR, no cap   (the LOCKED live keeper)
//    0.75xATR        : 0.75*ATR, no cap
//    0.50xATR        : 0.50*ATR, no cap
//    cap20pt / cap12pt (v1.2) / cap8pt : 1.00*ATR capped at 20 / 12 / 8 pt
//
//  Flags (all optional):
//    --days N      window length in TRADING days   (default 50)
//    --windows K   slide K windows across history   (default 1 = most recent)
//    --nq N        also show dollars at N NQ  contracts ($20/pt each)
//    --mnq M       also show dollars at M MNQ contracts ($2/pt each)
//  If neither --nq nor --mnq is given, defaults to 1 MNQ + 1 NQ.
//
//  Reuses data/nq-5m.json (run backtest-engine.js once to populate it).
//  DATA-ONLY / TopStep-compliant.
//    e.g.  node backtest-sweep.js --windows 5 --days 30 --nq 5 --mnq 1
// =============================================================
"use strict";

const fs = require("fs");
const path = require("path");
require("./public/indicators.js");
const I = globalThis.Indicators;

const RULESET = JSON.parse(fs.readFileSync(path.join(__dirname, "strategy-ruleset.json"), "utf8"));
const DATA_FILE = path.join(__dirname, "data", "nq-5m.json");
const PV = RULESET.instrument.point_value_usd; // { NQ:20, MNQ:2 }
const IND = RULESET.indicators, ENTRY = RULESET.entry;
const ADX_MAX = 25;
const DLL = RULESET.risk.topstep_50k_combine.daily_loss_limit_usd; // $1,000

const VARIANTS = [
  { name: "baseline (v1.1)", mult: 1.0, cap: null },
  { name: "0.75xATR", mult: 0.75, cap: null },
  { name: "0.50xATR", mult: 0.5, cap: null },
  { name: "cap20pt", mult: 1.0, cap: 20 },
  { name: "cap12pt (v1.2)", mult: 1.0, cap: 12 },
  { name: "cap8pt", mult: 1.0, cap: 8 },
];

function etParts(s) { const e = new Date(new Date(s * 1000).toLocaleString("en-US", { timeZone: "America/New_York" })); return { day: e.getDay(), mins: e.getHours() * 60 + e.getMinutes(), k: `${e.getFullYear()}-${e.getMonth()}-${e.getDate()}` }; }
const dayKeyOf = (s) => etParts(s).k;
const etDate = (s) => new Date(s * 1000).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" });
const isInRTH = (s) => { const p = etParts(s); return p.day !== 0 && p.day !== 6 && p.mins >= 570 && p.mins < 960; };

function precompute(bars) {
  const c = bars.map((b) => b.c), h = bars.map((b) => b.h), l = bars.map((b) => b.l);
  const basis = I.sma(c, IND.bollinger.length), dev = I.stdev(c, IND.bollinger.length);
  const lb = basis.map((v, k) => (v == null ? null : v - IND.bollinger.mult * dev[k]));
  const ub = basis.map((v, k) => (v == null ? null : v + IND.bollinger.mult * dev[k]));
  const rsi = I.rsi(c, IND.rsi.length);
  const { adx } = I.dmi(h, l, c, IND.adx.length, IND.adx.length);
  const ema = I.ema(c, IND.ema_trend.length);
  const atr = I.atr(h, l, c, IND.atr.length);
  const sL = c.map((x, k) => lb[k] != null && rsi[k] != null && x <= lb[k] && rsi[k] <= IND.rsi.oversold);
  const sS = c.map((x, k) => ub[k] != null && rsi[k] != null && x >= ub[k] && rsi[k] >= IND.rsi.overbought);
  const xu = I.crossover(c, lb), xd = I.crossunder(c, ub);
  return { c, basis, ema, adx, atr, sL, sS, xu, xd };
}

function buildSignals(bars, P, mult, cap) {
  const sig = new Array(bars.length).fill(null);
  for (let i = 1; i < bars.length; i++) {
    if (P.basis[i] == null || P.ema[i] == null || P.adx[i] == null || P.atr[i] == null) continue;
    if (!isInRTH(bars[i].t)) continue;
    if (!(P.adx[i] < ADX_MAX)) continue;
    const rl = P.xu[i] && I.barsSince(P.sL, i) <= ENTRY.confirm_bars;
    const rs = P.xd[i] && I.barsSince(P.sS, i) <= ENTRY.confirm_bars;
    let stopPts = mult * P.atr[i];
    if (cap != null) stopPts = Math.min(stopPts, cap);
    if (rl && P.c[i] > P.ema[i]) sig[i] = { dir: 1, entry: P.c[i], stop: P.c[i] - stopPts, target: P.basis[i], stopPts };
    else if (rs && P.c[i] < P.ema[i]) sig[i] = { dir: -1, entry: P.c[i], stop: P.c[i] + stopPts, target: P.basis[i], stopPts };
  }
  return sig;
}

function simulateTrade(bars, ei, s) {
  const d = dayKeyOf(bars[ei].t), L = s.dir === 1, e = s.entry;
  for (let k = ei + 1; k < bars.length; k++) {
    if (dayKeyOf(bars[k].t) !== d) break;
    const b = bars[k];
    if (L ? b.l <= s.stop : b.h >= s.stop) return { pts: L ? s.stop - e : e - s.stop, ei: k };
    if (L ? b.h >= s.target : b.l <= s.target) return { pts: L ? s.target - e : e - s.target, ei: k };
  }
  let last = ei;
  for (let k = ei + 1; k < bars.length && dayKeyOf(bars[k].t) === d; k++) last = k;
  return { pts: L ? bars[last].c - e : e - bars[last].c, ei: last };
}

function runVariant(bars, P, v) {
  const sig = buildSignals(bars, P, v.mult, v.cap);
  const trades = [];
  let i = 1;
  while (i < bars.length) {
    if (sig[i]) { const r = simulateTrade(bars, i, sig[i]); trades.push({ k: dayKeyOf(bars[i].t), pts: r.pts }); i = r.ei + 1; }
    else i++;
  }
  const wins = trades.filter((t) => t.pts > 0), gW = wins.reduce((s, t) => s + t.pts, 0), gL = Math.abs(trades.filter((t) => t.pts <= 0).reduce((s, t) => s + t.pts, 0));
  const netPts = trades.reduce((s, t) => s + t.pts, 0), worstPts = trades.length ? Math.min(...trades.map((t) => t.pts)) : 0;
  const byDay = new Map(); for (const t of trades) byDay.set(t.k, (byDay.get(t.k) || 0) + t.pts);
  const worstDayPts = trades.length ? Math.min(0, ...byDay.values()) : 0;
  return { n: trades.length, winRate: trades.length ? (wins.length / trades.length) * 100 : 0, pf: gL > 0 ? gW / gL : (gW > 0 ? Infinity : 0), netPts, worstPts, worstDayPts };
}

const m = (x) => (x >= 0 ? "+$" : "-$") + Math.abs(Math.round(x)).toLocaleString();
const f = (x, d = 0) => Number(x).toFixed(d);
function argNum(name) { const a = process.argv.find((x) => x.startsWith(name)); if (!a) return null; return parseInt(a.split("=")[1] || process.argv[process.argv.indexOf(a) + 1], 10); }

(function main() {
  if (!fs.existsSync(DATA_FILE)) { console.error("No data/nq-5m.json — run `node backtest-engine.js` first."); process.exit(1); }
  const allBars = JSON.parse(fs.readFileSync(DATA_FILE, "utf8"));

  const winLen = argNum("--days") || 50;
  const nWin = argNum("--windows") || 1;
  const nq = argNum("--nq"), mnq = argNum("--mnq");
  const sizes = (nq || mnq)
    ? [...(nq ? [{ label: `${nq} NQ`, pt: nq * PV.NQ }] : []), ...(mnq ? [{ label: `${mnq} MNQ`, pt: mnq * PV.MNQ }] : [])]
    : [{ label: "1 MNQ", pt: PV.MNQ }, { label: "1 NQ", pt: PV.NQ }];

  const allKeys = [...new Set(allBars.map((b) => dayKeyOf(b.t)))];
  const total = allKeys.length;
  const maxStart = Math.max(0, total - winLen);
  const starts = nWin <= 1 ? [maxStart] : Array.from({ length: nWin }, (_, i) => Math.round((i * maxStart) / (nWin - 1)));

  console.log(`\nMean-Rev stop-variant sweep — ${nWin} window(s) of ${winLen} trading days, across ${total} days of NQ 5-min history.`);
  console.log(`Sizes: ${sizes.map((s) => s.label).join("  +  ")}.  Entry/target/filters identical across rows; ONLY the stop differs.`);
  if (nWin > 1) console.log(`(Only ${total} days available, so 30-day windows OVERLAP in the middle — each just STARTS at a different point.)`);

  const colHdr = "Variant".padEnd(17) + "Trd Win%  PF  " + sizes.map((s) => ("Net " + s.label).padStart(11) + ("WDay " + s.label).padStart(13)).join("");

  const agg = new Map(VARIANTS.map((v) => [v.name, []])); // variant -> [r per window]

  starts.forEach((start, wi) => {
    const keys = new Set(allKeys.slice(start, start + winLen));
    const bars = allBars.filter((b) => keys.has(dayKeyOf(b.t)));
    const P = precompute(bars);
    console.log(`\n──────────── Window ${wi + 1}/${starts.length}: ${etDate(bars[0].t)} → ${etDate(bars[bars.length - 1].t)}  (${keys.size} days, ${bars.length} bars) ────────────`);
    console.log(colHdr);
    console.log("-".repeat(colHdr.length));
    for (const v of VARIANTS) {
      const r = runVariant(bars, P, v);
      agg.get(v.name).push(r);
      let line = v.name.padEnd(17) + String(r.n).padStart(3) + " " + (f(r.winRate) + "%").padStart(4) + " " + (r.pf === Infinity ? "inf" : f(r.pf, 2)).padStart(5) + " ";
      for (const s of sizes) {
        const wday = r.worstDayPts * s.pt;
        const breach = wday < -DLL ? "!" : " "; // "!" = worst day breaches TopStep $1,000 daily loss limit
        line += m(r.netPts * s.pt).padStart(11) + (m(wday) + breach).padStart(13);
      }
      console.log(line);
    }
  });
  console.log(`\nNQ = $20/pt · MNQ = $2/pt.  "!" after a worst-day = it breaches TopStep's $${DLL.toLocaleString()} daily loss limit (account-ending).`);

  // ---- Aggregate scorecard across all windows, per size ----
  for (const s of sizes) {
    console.log(`\n═══════════ SCORECARD @ ${s.label} (across ${starts.length} windows) ═══════════`);
    const hdr = "Variant".padEnd(17) + "TotNet".padStart(10) + "AvgNet".padStart(9) + "WorstWin".padStart(10) + "  Win+  Breach  WorstDay";
    console.log(hdr);
    console.log("-".repeat(hdr.length));
    const scored = VARIANTS.map((v) => {
      const rs = agg.get(v.name);
      const nets = rs.map((r) => r.netPts * s.pt);
      const totNet = nets.reduce((a, b) => a + b, 0);
      const winsPos = nets.filter((x) => x > 0).length;
      const worstWin = Math.min(...nets);
      const worstDay = Math.min(...rs.map((r) => r.worstDayPts * s.pt));
      const breaches = rs.filter((r) => r.worstDayPts * s.pt < -DLL).length;
      return { name: v.name, totNet, avgNet: totNet / rs.length, worstWin, winsPos, breaches, worstDay, nWin: rs.length };
    });
    // Best = combine-safe FIRST (fewest breaches), then most robust (windows positive), then highest total net.
    const ranked = [...scored].sort((a, b) => a.breaches - b.breaches || b.winsPos - a.winsPos || b.totNet - a.totNet);
    for (const x of scored) {
      const star = x === ranked[0] ? "  ★ BEST" : (x.breaches > 0 ? "  ✗ breaches limit" : "");
      console.log(
        x.name.padEnd(17) + m(x.totNet).padStart(10) + m(x.avgNet).padStart(9) + m(x.worstWin).padStart(10) +
        ("  " + x.winsPos + "/" + x.nWin).padStart(6) + String(x.breaches).padStart(7) + "  " + m(x.worstDay).padStart(8) + star
      );
    }
    const w = ranked[0];
    console.log(`→ Best @ ${s.label}: ${w.name} — ${w.breaches} breaches, positive in ${w.winsPos}/${w.nWin} windows, total ${m(w.totNet)} (avg ${m(w.avgNet)}/window), worst day ${m(w.worstDay)}.`);
  }
  console.log(`\nRanking rule: combine-safe FIRST (fewest daily-limit breaches), then robustness (windows positive), then total net.`);
  console.log(`Baseline = the LOCKED live v1.1. Small-sample caveat: short windows, one instrument — directional, NOT a multi-year verdict.`);
})();
