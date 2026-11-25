// =============================================================
//  power-hour-variants.js — test the 5 improvement ideas (A-E) from journal
//  entry (g) against BASELINE Power-hour (#42), on the 13-day chart first.
//
//    Baseline : 15:00-15:45 ET, trend-aligned vs EMA200 + momentum,
//               stop 1.2xATR / target 1.8xATR, FLAT size, no gate.
//    A. Vol-normalized sizing : risk a fixed $/trade (size = inverse of the
//       1.2xATR stop distance), mean size matched ~5 MNQ. Should cut maxDD$.
//    B. Regime gate           : only enter when ADX(14) > 20 (trade trend,
//       sit out the chop).
//    C. Circuit breaker       : max 1 Power-hour trade per day.
//    D. Breakeven stop        : raise stop to entry once price reaches +1R
//       (conservative: armed on a CLOSED bar, no intrabar lookahead).
//    E. Portfolio             : Power-hour + mean-rev v1.1 combined equity.
//
//  Reuses lab-new4.js's exact entry signals + exit model, and public/meanrev.js
//  (the LOCKED v1.1). DATA-ONLY: reads a local CSV, never places an order.
//  Run:  node power-hour-variants.js  [optional csv path, default = 13-day]
// =============================================================
"use strict";

require("./public/indicators.js");   // -> globalThis.Indicators
require("./public/meanrev.js");      // -> globalThis.MeanRev (needs Indicators)
const fs = require("fs");
const Lab = require("./lab-new4.js");
const Yahoo = require("./yahoo.js");
const I = globalThis.Indicators, MeanRev = globalThis.MeanRev;

// data source: "58"/"yahoo" -> Yahoo NQ=F 5m 60d (the journal's 58-day baseline);
// otherwise a CSV path; default = the 13-day MNQ CSV.
const ARG = process.argv[2];
const USE_YAHOO = ARG === "58" || ARG === "yahoo";
const CSV = (ARG && !USE_YAHOO) ? ARG : Lab.CSV_13;
const KEY = "powerHour";
const PV = 2;                         // $/pt per 1 MNQ
const REF = 5;                        // reference size for flat variants (5 MNQ)
const MLL = Lab.MLL, DLL = Lab.DLL;
const f = (x, d = 0) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));
const money = (x) => (x >= 0 ? "+$" : "-$") + f(Math.abs(x), 0);

// RTH helper rebuilt from Lab.etParts (Lab doesn't export isInRTH)
function inRTH(t) { const p = Lab.etParts(t); return p.day !== 0 && p.day !== 6 && p.mins >= 570 && p.mins < 960; }

// generic tally over an ordered list of {date, pnl} ($ already scaled)
function tally(trades) {
  const wins = trades.filter((t) => t.pnl > 0);
  const gW = wins.reduce((s, t) => s + t.pnl, 0);
  const gL = Math.abs(trades.filter((t) => t.pnl <= 0).reduce((s, t) => s + t.pnl, 0));
  let cum = 0, peak = 0, maxDD = 0;
  for (const t of trades) { cum += t.pnl; peak = Math.max(peak, cum); maxDD = Math.max(maxDD, peak - cum); }
  const byDay = new Map();
  for (const t of trades) byDay.set(t.date, (byDay.get(t.date) || 0) + t.pnl);
  const worstDay = trades.length ? Math.min(0, ...byDay.values()) : 0;
  return { n: trades.length, winPct: trades.length ? wins.length / trades.length * 100 : 0,
    pf: gL > 0 ? gW / gL : (gW > 0 ? Infinity : 0), net: cum, maxDD, worstDay };
}

// plain exit sim — identical rules to Lab.simulateTrade (stop-first on ties)
function plainSim(bars, entryIdx, sig) {
  const isLong = sig.dir === 1, entry = sig.entry, startDay = Lab.dayKeyOf(bars[entryIdx].t);
  for (let k = entryIdx + 1; k < bars.length; k++) {
    if (Lab.dayKeyOf(bars[k].t) !== startDay || !inRTH(bars[k].t)) { const px = bars[k - 1].c; return { pts: isLong ? px - entry : entry - px, exitIdx: k - 1 }; }
    const b = bars[k];
    if (isLong ? b.l <= sig.stop : b.h >= sig.stop) return { pts: isLong ? sig.stop - entry : entry - sig.stop, exitIdx: k };
    if (isLong ? b.h >= sig.target : b.l <= sig.target) return { pts: isLong ? sig.target - entry : entry - sig.target, exitIdx: k };
  }
  const px = bars[bars.length - 1].c; return { pts: isLong ? px - entry : entry - px, exitIdx: bars.length - 1 };
}

// breakeven exit sim (D): once a CLOSED bar trades +1R in our favor, stop -> entry
function beSim(bars, entryIdx, sig) {
  const isLong = sig.dir === 1, entry = sig.entry, startDay = Lab.dayKeyOf(bars[entryIdx].t);
  const R = Math.abs(entry - sig.stop); let stop = sig.stop, armed = false;
  for (let k = entryIdx + 1; k < bars.length; k++) {
    if (Lab.dayKeyOf(bars[k].t) !== startDay || !inRTH(bars[k].t)) { const px = bars[k - 1].c; return { pts: isLong ? px - entry : entry - px, exitIdx: k - 1 }; }
    const b = bars[k];
    if (isLong ? b.l <= stop : b.h >= stop) return { pts: isLong ? stop - entry : entry - stop, exitIdx: k };
    if (isLong ? b.h >= sig.target : b.l <= sig.target) return { pts: isLong ? sig.target - entry : entry - sig.target, exitIdx: k };
    if (!armed && (isLong ? b.h >= entry + R : b.l <= entry - R)) { armed = true; stop = entry; } // arm for NEXT bar
  }
  const px = bars[bars.length - 1].c; return { pts: isLong ? px - entry : entry - px, exitIdx: bars.length - 1 };
}

// walk a signal array with a chosen sim -> ledger of {date, pts, idx, sig}
function walk(bars, sigArr, sim) {
  const out = []; let i = 1;
  while (i < bars.length) {
    if (sigArr[i] && inRTH(bars[i].t)) { const r = sim(bars, i, sigArr[i]); out.push({ date: Lab.dayKeyOf(bars[i].t), pts: r.pts, idx: i, sig: sigArr[i] }); i = r.exitIdx + 1; }
    else i++;
  }
  return out;
}

(async function () {
  let bars, srcLabel;
  if (USE_YAHOO) {
    srcLabel = "Yahoo NQ=F 5m (58-day)";
    try { bars = await Yahoo.fetchBars({ interval: "5m", range: "60d" }); }
    catch (e) { console.error(`Yahoo fetch failed (${e.message}); using cached data/nq-5m.json`); bars = JSON.parse(fs.readFileSync(__dirname + "/data/nq-5m.json", "utf8")); }
  } else {
    srcLabel = CSV.split(/[\\/]/).pop();
    bars = Lab.loadCsv(CSV);
  }
  const dayKeys = [...new Set(bars.map((b) => Lab.dayKeyOf(b.t)))];
  const high = bars.map((b) => b.h), low = bars.map((b) => b.l), close = bars.map((b) => b.c);
  const adx = I.dmi(high, low, close, 14, 14).adx;
  const S = Lab.buildAll(bars);
  const sig = S[KEY];

  console.log(`POWER-HOUR (#42) — BASELINE vs 5 IMPROVEMENTS (A-E).  Data: ${srcLabel}`);
  console.log(`${bars.length} bars / ${dayKeys.length} ET trading days.  $ shown at ${REF} MNQ-equivalent ($${PV}/pt/contract).  MLL $${MLL}, DLL $${DLL}.\n`);

  const rows = [];
  const push = (name, trades, extra = "") => { const t = tally(trades); rows.push({ name, t, extra }); };

  // ---- baseline (flat 5) ----
  const base = walk(bars, sig, plainSim);
  push("Baseline (flat 5)", base.map((x) => ({ date: x.date, pnl: x.pts * PV * REF })));

  // ---- A: vol-normalized sizing (mean size ~5) ----
  const stopDists = base.map((x) => Math.abs(x.sig.entry - x.sig.stop));
  const meanStop = stopDists.reduce((s, d) => s + d, 0) / (stopDists.length || 1);
  let sizes = [];
  const aTrades = base.map((x, k) => {
    let c = REF * meanStop / stopDists[k];           // inverse-vol size, centered on 5
    c = Math.max(1, Math.min(15, c)); sizes.push(c);
    return { date: x.date, pnl: x.pts * PV * c };
  });
  const avgSize = sizes.reduce((s, c) => s + c, 0) / (sizes.length || 1);
  push("A. Vol-normalized size", aTrades, `avg ${f(avgSize, 1)} MNQ, fixed ~$${f(REF * meanStop * PV, 0)}/trade risk`);

  // ---- B: ADX(14) > 20 gate ----
  const gated = sig.map((v, i) => (v && adx[i] != null && adx[i] > 20) ? v : null);
  const bLed = walk(bars, gated, plainSim);
  push("B. ADX>20 gate (flat 5)", bLed.map((x) => ({ date: x.date, pnl: x.pts * PV * REF })));

  // ---- C: max 1 trade/day ----
  const seen = new Set();
  const cTrades = base.filter((x) => (seen.has(x.date) ? false : (seen.add(x.date), true)))
    .map((x) => ({ date: x.date, pnl: x.pts * PV * REF }));
  push("C. Max 1 trade/day (5)", cTrades);

  // ---- D: breakeven-after-1R stop ----
  const dLed = walk(bars, sig, beSim);
  push("D. Breakeven stop (5)", dLed.map((x) => ({ date: x.date, pnl: x.pts * PV * REF })));

  // ---- E: portfolio Power-hour + v1.1 (each flat 5) ----
  const v11 = []; let i = 1;
  while (i < bars.length) {
    const ms = MeanRev.computeMeanRev(bars, i);
    if (ms.signal === "BUY" || ms.signal === "SELL") {
      const r = plainSim(bars, i, { dir: ms.dir, entry: ms.entry, stop: ms.stop, target: ms.target });
      v11.push({ date: Lab.dayKeyOf(bars[i].t), exitT: bars[r.exitIdx].t, pnl: r.pts * PV * REF }); i = r.exitIdx + 1;
    } else i++;
  }
  const phPort = base.map((x) => ({ date: x.date, exitT: bars[x.idx].t, pnl: x.pts * PV * REF }));
  const combined = [...phPort, ...v11].sort((a, b) => a.exitT - b.exitT);
  push("E. Portfolio PH+v1.1 (5 ea)", combined, `v1.1 alone: ${v11.length} trades, ${money(tally(v11).net)}`);

  // ---- table ----
  const hdr = "Variant".padEnd(28) + "Trd".padStart(4) + "Win%".padStart(6) + "PF".padStart(6) +
    "Net".padStart(10) + "MaxDD".padStart(9) + "WorstDay".padStart(10) + "  MLL-safe?";
  console.log(hdr); console.log("-".repeat(hdr.length));
  const base5DD = rows[0].t.maxDD;
  for (const r of rows) {
    const safe = r.t.maxDD < MLL ? "yes" : "NO (>$2k)";
    console.log(
      r.name.padEnd(28) + String(r.t.n).padStart(4) + (f(r.t.winPct, 0) + "%").padStart(6) +
      (r.t.pf === Infinity ? "inf" : f(r.t.pf, 2)).padStart(6) + money(r.t.net).padStart(10) +
      ("$" + f(r.t.maxDD, 0)).padStart(9) + money(-Math.abs(r.t.worstDay)).padStart(10) + "  " + safe +
      (r.extra ? "   [" + r.extra + "]" : "")
    );
  }

  console.log(`\nVERDICT (${dayKeys.length}-day sample = ${srcLabel}; score maxDD-vs-$${MLL}-MLL first, then net/PF):`);
  console.log(`  - Baseline maxDD@5 here = $${f(base5DD, 0)}. A fix earns its place only if it KEEPS net while CUTTING maxDD without gutting trade count.`);
  console.log(`  - Keep only what survives across the 13-day, 58-day AND 90-day samples on net AND maxDD; each filter spends degrees of freedom.`);
})().catch((e) => { console.error("power-hour-variants error:", e.stack || e.message); process.exit(1); });
