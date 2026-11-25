// =============================================================
//  power-hour-firstday.js — ODDS the bot has a BAD first day, and whether a
//  first day (zero buffer) could even breach the account.
//
//  Day 1 has no banked profit, so the trailing MLL floor sits at the full
//  -$2,000 and the DLL at -$1,000. We tabulate the per-day P&L distribution of
//  the ADX>20-gated Power-hour and report:
//    - P(first day is a LOSING day)             = lossDays / activeDays
//    - P(first day breaches MLL on its own)     = days worse than -$2,000
//    - P(first day is DLL-stopped, <= -$1,000)
//  at flat 3 (LOCKED) and flat 5. Order is i.i.d. across active days, so any
//  given day is equally likely to be "first" — these counts ARE the odds.
//
//  Reuses lab-new4.js's exact signal + exit model. DATA-ONLY.
//  Run:  node power-hour-firstday.js  [optional csv path, default = 90-day NQ1!]
// =============================================================
"use strict";

require("./public/indicators.js");
const Lab = require("./lab-new4.js");
const I = globalThis.Indicators;

const CSV = process.argv[2] || "C:\\Users\\kaide\\Downloads\\CME_MINI_DL_NQ1!, 5.csv";
const PV = 2, MLL = Lab.MLL, DLL = Lab.DLL;
const f = (x, d = 0) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));
const money = (x) => (x >= 0 ? "+$" : "-$") + f(Math.abs(x), 0);
const pctF = (n, d) => (d ? f(n / d * 100, 1) : "0.0") + "%";

(function () {
  const bars = Lab.loadCsv(CSV);
  const high = bars.map((b) => b.h), low = bars.map((b) => b.l), close = bars.map((b) => b.c);
  const adx = I.dmi(high, low, close, 14, 14).adx;
  const S = Lab.buildAll(bars);
  const gated = S.powerHour.map((v, i) => (v && adx[i] != null && adx[i] > 20) ? v : null);
  const ledger = Lab.runLedger(bars, gated);

  const dayMap = new Map();
  for (const t of ledger) { dayMap.set(t.date, (dayMap.get(t.date) || 0) + t.pts); }
  const dayPts = [...dayMap.values()];          // per-day P&L in POINTS
  const D = dayPts.length;

  console.log(`POWER-HOUR + ADX>20 GATE — ODDS OF A BAD FIRST DAY.  Data: ${CSV.split(/[\\/]/).pop()}`);
  console.log(`${ledger.length} trades over ${D} active days. Day 1 has NO buffer: MLL floor = -$${MLL}, DLL = -$${DLL}/day.\n`);

  for (const size of [3, 5]) {
    const pnl = dayPts.map((p) => p * size * PV).sort((a, b) => a - b);
    const lossDays = pnl.filter((x) => x < 0).length;
    const flatDays = pnl.filter((x) => x === 0).length;
    const winDays = pnl.filter((x) => x > 0).length;
    const worst = pnl[0], best = pnl[pnl.length - 1];
    const mllBreach = pnl.filter((x) => x <= -MLL).length;   // single day that alone fails the trailing MLL
    const dllStop = pnl.filter((x) => x <= -DLL).length;     // single day that hits the daily loss limit
    console.log(`── flat ${size} MNQ ${"─".repeat(40)}`);
    console.log(`  Day outcomes:           ${winDays} up / ${lossDays} down / ${flatDays} flat   (worst ${money(worst)}, best ${money(best)})`);
    console.log(`  P(first day is a LOSS): ${pctF(lossDays, D)}   (${lossDays}/${D} active days are down days)`);
    console.log(`  P(first day breaches MLL alone, <= -$${MLL}): ${pctF(mllBreach, D)}   (${mllBreach}/${D})`);
    console.log(`  P(first day hits DLL, <= -$${DLL}):           ${pctF(dllStop, D)}   (${dllStop}/${D})`);
    console.log(`  -> Even the WORST observed day (${money(worst)}) ${worst <= -MLL ? "WOULD" : "could NOT"} breach MLL day-1, and ${worst <= -DLL ? "WOULD" : "would NOT"} hit the DLL.\n`);
  }

  console.log(`READ: a "bad first day" = a losing first day. The odds equal the share of active days that are down days,`);
  console.log(`because any of the ${D} days is equally likely to land first. The bigger point: with no day in this sample`);
  console.log(`losing more than ~-$980 (@5) / -$588 (@3), a SINGLE bad first day cannot fail the account — it'd take a`);
  console.log(`back-to-back losing CLUSTER early, which is exactly what the 10k-permutation MLL-fail% (flat3 0.5% / flat5 6.4%) measures.`);
})();
