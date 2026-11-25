// =============================================================
//  power-hour-eval.js — HOW LONG to pass a TopStep $50K Combine with the
//  "Power-hour + ADX>20 gate" keeper (journal entry (k))?
//
//  The eval is UNTIMED, so "how long" = trading days until +$3,000 is banked
//  WITHOUT tripping the $2,000 trailing MLL or the $1,000 daily loss limit.
//  We answer two ways on the 90-day chart:
//    (1) REAL chronological order — pass day at flat 5 / 3 / 1 MNQ.
//    (2) 10k return-order permutations — pass%, and the DISTRIBUTION of pass
//        day (p25 / median / p75) so we give a range, not a point guess.
//  Pass day is in ACTIVE trading days (days the strategy actually traded);
//  we also convert to calendar weeks using the gated trade frequency.
//
//  Reuses lab-new4.js's exact signal + exit model. DATA-ONLY.
//  Run:  node power-hour-eval.js  [optional csv path, default = 90-day NQ1!]
// =============================================================
"use strict";

require("./public/indicators.js");
const Lab = require("./lab-new4.js");
const I = globalThis.Indicators;

const CSV = process.argv[2] || "C:\\Users\\kaide\\Downloads\\CME_MINI_DL_NQ1!, 5.csv";
const PV = 2, MLL = 2000, DLL = 1000, TARGET = 3000;
const f = (x, d = 0) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));

function simulate(days, size) {
  let realized = 0, peak = 0;
  for (let d = 0; d < days.length; d++) {
    let dayPnL = 0;
    for (const pts of days[d]) {
      const pnl = pts * size * PV;
      realized += pnl; dayPnL += pnl;
      if (realized > peak) peak = realized;
      if (realized <= Math.min(peak - MLL, 0)) return { outcome: "MLL", passDayIdx: null };
      if (dayPnL <= -DLL) return { outcome: "DLL", passDayIdx: null };
      if (realized >= TARGET) return { outcome: "PASS", passDayIdx: d };
    }
  }
  return { outcome: "INCOMPLETE", passDayIdx: null };
}
function mulberry32(a) { return function () { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function shuffled(arr, rng) { const a = arr.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rng() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }
const pct = (sorted, p) => sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))] : null;

(function () {
  const bars = Lab.loadCsv(CSV);
  const high = bars.map((b) => b.h), low = bars.map((b) => b.l), close = bars.map((b) => b.c);
  const adx = I.dmi(high, low, close, 14, 14).adx;
  const calDays = new Set(bars.map((b) => Lab.dayKeyOf(b.t))).size;
  const S = Lab.buildAll(bars);
  const gated = S.powerHour.map((v, i) => (v && adx[i] != null && adx[i] > 20) ? v : null);
  const ledger = Lab.runLedger(bars, gated);

  const dayMap = new Map();
  for (const t of ledger) { if (!dayMap.has(t.date)) dayMap.set(t.date, []); dayMap.get(t.date).push(t.pts); }
  const days = [...dayMap.values()];
  const activeDays = days.length;
  const activePerWeek = 5 * (activeDays / calDays);   // gated days per calendar week
  const cal = (active) => active == null ? null : active * (calDays / activeDays);  // active-day# -> calendar trading days

  console.log(`POWER-HOUR + ADX>20 GATE — TIME-TO-PASS a $50K Combine.  Data: ${CSV.split(/[\\/]/).pop()}`);
  console.log(`${ledger.length} trades over ${activeDays} ACTIVE days within ${calDays} calendar trading days (~${f(activePerWeek, 1)} trade-days/week).`);
  console.log(`Pass = +$${TARGET}; fail = $${MLL} trailing MLL or $${DLL}/day DLL.\n`);

  // (1) real chronological order
  console.log(`(1) REAL CHRONOLOGICAL ORDER (the actual Mar->Jun sequence):`);
  for (const size of [5, 3, 1]) {
    const r = simulate(days, size);
    console.log(`  flat ${size} MNQ -> ${r.outcome.padEnd(11)}` +
      (r.outcome === "PASS" ? `passed on active day #${r.passDayIdx + 1}  (~${f(cal(r.passDayIdx + 1), 0)} calendar trading days ≈ ${f(cal(r.passDayIdx + 1) / 5, 1)} weeks)` : ""));
  }

  // (2) return-order distribution
  const N = 10000, rng = mulberry32(12345);
  console.log(`\n(2) ${N} RETURN-ORDER PERMUTATIONS — pass% and how many active days it takes:`);
  console.log("  " + "Size".padEnd(10) + "Pass%".padStart(7) + "FailMLL%".padStart(10) + "NoReach%".padStart(10) +
    "  pass-day (active)  ->  calendar weeks");
  for (const size of [5, 3, 1]) {
    let pass = 0, mll = 0, dll = 0, inc = 0; const pd = [];
    for (let n = 0; n < N; n++) {
      const r = simulate(shuffled(days, rng), size);
      if (r.outcome === "PASS") { pass++; pd.push(r.passDayIdx + 1); }
      else if (r.outcome === "MLL") mll++; else if (r.outcome === "DLL") dll++; else inc++;
    }
    pd.sort((a, b) => a - b);
    const p25 = pct(pd, 0.25), p50 = pct(pd, 0.5), p75 = pct(pd, 0.75);
    const wk = (a) => a == null ? "—" : f(cal(a) / 5, 1);
    console.log("  " + ("flat " + size).padEnd(10) + (f(pass / N * 100, 1) + "%").padStart(7) +
      (f(mll / N * 100, 1) + "%").padStart(10) + (f((dll + inc) / N * 100, 1) + "%").padStart(10) +
      `   p25 #${p25}  med #${p50}  p75 #${p75}    ->   ${wk(p25)}–${wk(p75)} wk (med ${wk(p50)})`);
  }

  console.log(`\nREAD: "active day" = a day the gated strategy actually placed a trade (~${f(activePerWeek, 1)}/wk), NOT every calendar day.`);
  console.log(`Caveats: untimed eval, so these are EDGE-time estimates. TopStep may add a minimum-trading-days and/or consistency rule (no single day > ~50% of profit) — VERIFY in current rules; a single-day spike could force more days than the edge alone needs. All samples are net-up regimes.`);
})();
