// =============================================================
//  power-hour-staged.js — does STAGED sizing fix Power-hour's return-order risk?
//
//  Finding from power-hour-drawdown.js: at flat 5 MNQ the worst $1,808 slide was
//  survivable ONLY because it came late, after a profit buffer was banked. If the
//  same losing cluster front-loaded, it would nearly fail the account. Proposed
//  fix: start the eval small (1-3 MNQ) and scale to 5 MNQ only once ~$2,000 is
//  banked — the point where TopStep's trailing MLL LOCKS at the $50k start.
//
//  This script tests that two ways on Power-hour (#42), full 58-day ledger:
//   1) CHRONOLOGICAL run with full $50K Combine rules enforced:
//        - trailing MLL: floor = min(peakProfit - 2000, 0)  (locks at break-even
//          once +$2,000 banked); account FAILS if profit <= floor.
//        - daily loss limit: FAIL if any day's running P&L <= -$1,000.
//        - PASS when profit first reaches +$3,000.
//   2) RETURN-ORDER STRESS TEST: randomly permute the ~34 trading days many times
//        and measure each scheme's PASS / FAIL-MLL / FAIL-DLL rate. This is the
//        real test of "what if the bad days came early."
//
//  Reuses lab-new4.js's exact strategy code + exit model. DATA-ONLY.
//  Run:  node power-hour-staged.js
// =============================================================
"use strict";

const fs = require("fs");
const Yahoo = require("./yahoo.js");
const Lab = require("./lab-new4.js");

const KEY = "powerHour";
const PV = 2;                 // $ per point per 1 MNQ
const MLL = 2000, DLL = 1000, TARGET = 3000;
const f = (x, d = 0) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));
const money = (x) => (x >= 0 ? "+$" : "-$") + f(Math.abs(x));

// sizing schemes: start size, the size to scale to, and the banked-$ threshold
const SCHEMES = [
  { name: "flat 1 MNQ", start: 1, scaled: 1, scaleAt: Infinity },
  { name: "flat 3 MNQ", start: 3, scaled: 3, scaleAt: Infinity },
  { name: "flat 5 MNQ", start: 5, scaled: 5, scaleAt: Infinity },
  { name: "staged 1->5 @ $2k", start: 1, scaled: 5, scaleAt: 2000 },
  { name: "staged 2->5 @ $2k", start: 2, scaled: 5, scaleAt: 2000 },
  { name: "staged 3->5 @ $2k", start: 3, scaled: 5, scaleAt: 2000 },
];

// simulate one account over an ordered list of days (each = array of trade pts).
// returns { outcome: PASS|MLL|DLL|INCOMPLETE, profit, peak, passDayIdx, scaledAt }
function simulate(days, scheme) {
  let realized = 0, peak = 0, scaled = false, scaledAt = null, passDayIdx = null;
  for (let d = 0; d < days.length; d++) {
    let dayPnL = 0;
    for (const pts of days[d]) {
      const size = scaled ? scheme.scaled : scheme.start;
      const pnl = pts * size * PV;
      realized += pnl; dayPnL += pnl;
      if (realized > peak) peak = realized;
      const floor = Math.min(peak - MLL, 0);
      if (realized <= floor) return { outcome: "MLL", profit: realized, peak, passDayIdx, scaledAt };
      if (dayPnL <= -DLL) return { outcome: "DLL", profit: realized, peak, passDayIdx, scaledAt };
      if (realized >= TARGET && passDayIdx == null) { passDayIdx = d; return { outcome: "PASS", profit: realized, peak, passDayIdx, scaledAt }; }
      if (!scaled && realized >= scheme.scaleAt) { scaled = true; scaledAt = d; }
    }
  }
  return { outcome: "INCOMPLETE", profit: realized, peak, passDayIdx, scaledAt };
}

// seedable PRNG (mulberry32) for reproducible shuffles
function mulberry32(a) { return function () { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function shuffled(arr, rng) { const a = arr.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rng() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }

(async () => {
  let bars = null;
  try { bars = await Yahoo.fetchBars({ interval: "5m", range: "60d" }); }
  catch (e) { console.error(`Yahoo live fetch failed (${e.message}); using cached data/nq-5m.json`); bars = JSON.parse(fs.readFileSync(__dirname + "/data/nq-5m.json", "utf8")); }

  const S = Lab.buildAll(bars);
  const ledger = Lab.runLedger(bars, S[KEY]);

  // group consecutive trades into trading days (ledger is chronological)
  const dayMap = new Map();
  for (const t of ledger) { if (!dayMap.has(t.date)) dayMap.set(t.date, []); dayMap.get(t.date).push(t.pts); }
  const days = [...dayMap.values()];          // chronological day blocks
  console.log(`POWER-HOUR (#42) STAGED-SIZING TEST — ${ledger.length} trades across ${days.length} trading days.`);
  console.log(`$50K Combine: trailing MLL $${MLL} (locks at break-even once +$${MLL} banked), DLL $${DLL}/day, pass = +$${TARGET}.\n`);

  // ---- 1) chronological, real order ----
  console.log(`(1) REAL CHRONOLOGICAL ORDER`);
  console.log("  " + "Scheme".padEnd(20) + "Outcome".padStart(12) + "FinalProfit".padStart(13) + "Peak".padStart(10) + "Pass day".padStart(10) + "Scaled day".padStart(12));
  for (const sc of SCHEMES) {
    const r = simulate(days, sc);
    console.log("  " + sc.name.padEnd(20) + r.outcome.padStart(12) + money(r.profit).padStart(13) + money(r.peak).padStart(10) +
      (r.passDayIdx == null ? "—" : "#" + (r.passDayIdx + 1)).padStart(10) + (r.scaledAt == null ? "—" : "#" + (r.scaledAt + 1)).padStart(12));
  }

  // ---- 2) return-order stress test ----
  const N = 10000;
  const rng = mulberry32(12345);
  console.log(`\n(2) RETURN-ORDER STRESS TEST — ${N} random permutations of the ${days.length} trading days`);
  console.log(`  (Tests: if the same days arrived in a different order, how often does the account PASS vs blow up?)`);
  console.log("  " + "Scheme".padEnd(20) + "Pass%".padStart(8) + "Fail-MLL%".padStart(11) + "Fail-DLL%".padStart(11) + "NoPass%".padStart(9) + "MedPassDay".padStart(12));
  for (const sc of SCHEMES) {
    let pass = 0, mll = 0, dll = 0, inc = 0; const passDays = [];
    for (let n = 0; n < N; n++) {
      const r = simulate(shuffled(days, rng), sc);
      if (r.outcome === "PASS") { pass++; passDays.push(r.passDayIdx + 1); }
      else if (r.outcome === "MLL") mll++;
      else if (r.outcome === "DLL") dll++;
      else inc++;
    }
    passDays.sort((a, b) => a - b);
    const med = passDays.length ? passDays[Math.floor(passDays.length / 2)] : null;
    console.log("  " + sc.name.padEnd(20) + (f(pass / N * 100, 1) + "%").padStart(8) + (f(mll / N * 100, 1) + "%").padStart(11) +
      (f(dll / N * 100, 1) + "%").padStart(11) + (f(inc / N * 100, 1) + "%").padStart(9) + (med == null ? "—" : "#" + med).padStart(12));
  }

  console.log(`\nREAD: "Fail-MLL%" = share of orderings where a front-loaded losing cluster trips the $2,000 trailing limit before passing.`);
  console.log(`A lower Fail% at equal-or-better Pass% means the sizing scheme is more robust to the ORDER trades arrive in — the whole point of staging.`);
  console.log(`Caveat: permutations reuse THIS quarter's 34 days (same trades, reordered) — it isolates order risk, not regime risk. A non-trending quarter is still the untested frontier.`);
})().catch((e) => { console.error("power-hour-staged error:", e.stack || e.message); process.exit(1); });
