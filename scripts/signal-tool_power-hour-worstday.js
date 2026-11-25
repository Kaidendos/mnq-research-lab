// =============================================================
//  power-hour-worstday.js — WHEN did the ADX>20-gated Power-hour have its worst
//  day, how much profit was banked going INTO it, and could that day have
//  tripped the $2,000 trailing MLL? (i.e. "could I tank the DD?")
//
//  Walks the gated ledger in REAL chronological order, tracks realized profit +
//  equity peak + the trailing MLL floor = min(peak - 2000, 0). Finds the worst
//  single day at flat 3 (LOCKED eval size) and flat 5, and reports the buffer
//  that stood between that day's loss and an account breach.
//
//  Reuses lab-new4.js's exact signal + exit model. DATA-ONLY.
//  Run:  node power-hour-worstday.js  [optional csv path, default = 90-day NQ1!]
// =============================================================
"use strict";

require("./public/indicators.js");
const Lab = require("./lab-new4.js");
const I = globalThis.Indicators;

const CSV = process.argv[2] || "C:\\Users\\kaide\\Downloads\\CME_MINI_DL_NQ1!, 5.csv";
const PV = 2, MLL = Lab.MLL, DLL = Lab.DLL;
const f = (x, d = 0) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));
const money = (x) => (x >= 0 ? "+$" : "-$") + f(Math.abs(x), 0);
const ymd = (k) => { const s = String(k); return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6)}`; };

function analyze(days, size) {
  let realized = 0, peak = 0;
  let worst = { day: 0, dayKey: null, dayPnL: Infinity, before: 0, peakBefore: 0, floorBefore: 0 };
  for (let d = 0; d < days.length; d++) {
    const before = realized, peakBefore = peak, floorBefore = Math.min(peak - MLL, 0);
    const dayPnL = days[d].pts.reduce((s, p) => s + p * size * PV, 0);
    realized += dayPnL;
    if (realized > peak) peak = realized;
    if (dayPnL < worst.dayPnL) worst = { day: d + 1, dayKey: days[d].key, dayPnL, before, peakBefore, floorBefore };
  }
  return { worst, finalRealized: realized, finalPeak: peak };
}

(function () {
  const bars = Lab.loadCsv(CSV);
  const high = bars.map((b) => b.h), low = bars.map((b) => b.l), close = bars.map((b) => b.c);
  const adx = I.dmi(high, low, close, 14, 14).adx;
  const S = Lab.buildAll(bars);
  const gated = S.powerHour.map((v, i) => (v && adx[i] != null && adx[i] > 20) ? v : null);
  const ledger = Lab.runLedger(bars, gated);

  const dayMap = new Map();
  for (const t of ledger) { if (!dayMap.has(t.date)) dayMap.set(t.date, { key: t.date, pts: [] }); dayMap.get(t.date).pts.push(t.pts); }
  const days = [...dayMap.values()];

  console.log(`POWER-HOUR + ADX>20 GATE — WORST-DAY / DRAWDOWN CONTEXT.  Data: ${CSV.split(/[\\/]/).pop()}`);
  console.log(`${ledger.length} trades over ${days.length} active days, real chronological order. MLL $${MLL} (trails peak), DLL $${DLL}/day.\n`);

  for (const size of [3, 5]) {
    const { worst: w, finalRealized } = analyze(days, size);
    const equityAfter = w.before + w.dayPnL;            // realized profit right after the worst day
    const breachFloor = w.floorBefore;                  // MLL floor that applied going into the day
    const headroom = w.before - breachFloor;            // $ the day could lose before tripping MLL
    const tripped = equityAfter <= breachFloor;         // did/would this day breach the trailing MLL?
    const dllHit = w.dayPnL <= -DLL;                    // would DLL have stopped the day first?
    console.log(`── flat ${size} MNQ ${"─".repeat(40)}`);
    console.log(`  Worst day:            ${ymd(w.dayKey)}  (active day #${w.day} of ${days.length})  ${money(w.dayPnL)}`);
    console.log(`  Profit going INTO it: ${money(w.before)}   (equity peak so far ${money(w.peakBefore)})`);
    console.log(`  Trailing MLL floor:   ${money(breachFloor)}   -> buffer before breach = ${money(headroom)}`);
    console.log(`  After the worst day:  ${money(equityAfter)}   -> MLL breach? ${tripped ? "YES — account would fail" : "NO, survived"}`);
    console.log(`  DLL ($${DLL}/day) hit during the day? ${dllHit ? "YES — day would be cut at -$" + DLL : "no (day loss < DLL)"}`);
    console.log(`  (For reference, final realized over the full 90d = ${money(finalRealized)}.)\n`);
  }

  console.log(`READ: "buffer before breach" = how much that single day could have lost before the trailing MLL floor was hit,`);
  console.log(`given the profit already banked when the day started. A big worst-day is only dangerous if it lands EARLY, before a buffer exists.`);
  console.log(`Caveat: this is the REAL order. The 10k-permutation stress (power-hour-eval.js) already prices in the worst day arriving early:`);
  console.log(`that's exactly why flat 5 carries a 6.4% MLL-fail tail and flat 3 only 0.5%.`);
})();
