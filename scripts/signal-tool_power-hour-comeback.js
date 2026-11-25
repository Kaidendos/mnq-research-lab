// =============================================================
//  power-hour-comeback.js — given a LOSING first day, what are the odds the
//  ADX>20-gated Power-hour still PASSES the $50K Combine (+$3,000) without
//  breaching the $2,000 trailing MLL or $1,000 DLL?
//
//  Three views, flat 3 (LOCKED) and flat 5:
//   (A) Unconditional pass% (baseline, for comparison).
//   (B) P(pass | first day is a LOSS): 10k permutations, kept only when day[0] < 0.
//   (C) P(pass | WORST day is forced first): pin the single worst day at slot 0,
//       shuffle the remaining 47, 10k times — the harshest fair "bad start".
//
//  Reuses lab-new4.js's exact signal + exit model. DATA-ONLY.
//  Run:  node power-hour-comeback.js  [optional csv path, default = 90-day NQ1!]
// =============================================================
"use strict";

require("./public/indicators.js");
const Lab = require("./lab-new4.js");
const I = globalThis.Indicators;

const CSV = process.argv[2] || "C:\\Users\\kaide\\Downloads\\CME_MINI_DL_NQ1!, 5.csv";
const PV = 2, MLL = Lab.MLL, DLL = Lab.DLL, TARGET = 3000;
const f = (x, d = 0) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));
const money = (x) => (x >= 0 ? "+$" : "-$") + f(Math.abs(x), 0);

function simulate(days, size) {
  let realized = 0, peak = 0;
  for (let d = 0; d < days.length; d++) {
    let dayPnL = 0;
    for (const pts of days[d]) {
      const pnl = pts * size * PV;
      realized += pnl; dayPnL += pnl;
      if (realized > peak) peak = realized;
      if (realized <= Math.min(peak - MLL, 0)) return { outcome: "MLL", passDay: null };
      if (dayPnL <= -DLL) return { outcome: "DLL", passDay: null };
      if (realized >= TARGET) return { outcome: "PASS", passDay: d };
    }
  }
  return { outcome: "INCOMPLETE", passDay: null };
}
function mulberry32(a) { return function () { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function shuffled(arr, rng) { const a = arr.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rng() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }
const sumPts = (block, size) => block.reduce((s, p) => s + p * size * PV, 0);

(function () {
  const bars = Lab.loadCsv(CSV);
  const high = bars.map((b) => b.h), low = bars.map((b) => b.l), close = bars.map((b) => b.c);
  const adx = I.dmi(high, low, close, 14, 14).adx;
  const S = Lab.buildAll(bars);
  const gated = S.powerHour.map((v, i) => (v && adx[i] != null && adx[i] > 20) ? v : null);
  const ledger = Lab.runLedger(bars, gated);

  const dayMap = new Map();
  for (const t of ledger) { if (!dayMap.has(t.date)) dayMap.set(t.date, []); dayMap.get(t.date).push(t.pts); }
  const days = [...dayMap.values()];
  const D = days.length, N = 10000;

  console.log(`POWER-HOUR + ADX>20 GATE — CAN YOU COME BACK FROM A BAD FIRST DAY?  Data: ${CSV.split(/[\\/]/).pop()}`);
  console.log(`${ledger.length} trades / ${D} active days. Pass +$${TARGET}; fail $${MLL} trailing MLL or $${DLL}/day DLL. ${N} permutations each.\n`);

  for (const size of [3, 5]) {
    const rng = mulberry32(12345);
    // worst day index for view C
    let worstI = 0; for (let i = 1; i < D; i++) if (sumPts(days[i], size) < sumPts(days[worstI], size)) worstI = i;
    const worst$ = sumPts(days[worstI], size);

    // (A) unconditional + (B) conditional-on-losing-first-day, from the SAME permutation stream
    let aPass = 0, aTot = 0, bPass = 0, bTot = 0; const bPassDays = [];
    for (let n = 0; n < N; n++) {
      const perm = shuffled(days, rng);
      const r = simulate(perm, size);
      aTot++; if (r.outcome === "PASS") aPass++;
      if (sumPts(perm[0], size) < 0) { bTot++; if (r.outcome === "PASS") { bPass++; bPassDays.push(r.passDay + 1); } }
    }
    // (C) worst day pinned first, rest shuffled
    let cPass = 0; const rest = days.filter((_, i) => i !== worstI);
    for (let n = 0; n < N; n++) {
      const r = simulate([days[worstI], ...shuffled(rest, rng)], size);
      if (r.outcome === "PASS") cPass++;
    }
    bPassDays.sort((a, b) => a - b);
    const medB = bPassDays.length ? bPassDays[Math.floor(bPassDays.length / 2)] : null;

    console.log(`── flat ${size} MNQ ${"─".repeat(40)}`);
    console.log(`  (A) Unconditional pass%:                 ${f(aPass / aTot * 100, 1)}%`);
    console.log(`  (B) Pass% | first day is a LOSS:         ${f(bPass / bTot * 100, 1)}%   (over ${bTot} such draws; median pass on active day #${medB})`);
    console.log(`  (C) Pass% | WORST day (${money(worst$)}) forced FIRST: ${f(cPass / N * 100, 1)}%`);
    console.log(`      -> comeback cost vs unconditional: ${f((aPass / aTot - bPass / bTot) * 100, 1)} pts (any loss) / ${f((aPass / aTot - cPass / N) * 100, 1)} pts (worst-first).\n`);
  }

  console.log(`READ: (B) is the real-world "I had a red first day, am I cooked?" number. (C) is the worst fair case — the single`);
  console.log(`biggest losing day lands on day 1. The gap from (A) shows how little a bad open actually costs your pass odds:`);
  console.log(`a small early deficit just delays the target, it rarely causes the breach. Net-up sample caveat still applies.`);
})();
