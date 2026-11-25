// =============================================================
//  power-hour-drawdown.js — forensics on Power-hour (#42)'s worst drawdown.
//
//  Question: WHEN did the ~$1,800 max drawdown happen, and did banked profit
//  cover it (i.e., did equity stay above the starting balance the whole time,
//  or did the slide eat into the account's cushion)?
//
//  Walks the per-trade equity curve on the full 58-day Yahoo NQ=F 5m sample,
//  finds the single largest peak->trough slide, dates it, lists the losing
//  trades inside it, and reports whether the running equity ever dipped below
//  zero (= below the $50k start, the only thing that can fail the account).
//
//  TopStep $50K Combine framing: trailing MLL starts $2,000 below the start
//  and trails the equity PEAK upward. So a drawdown only endangers the account
//  if (a) it exceeds $2,000 from the peak, or (b) it happens before any profit
//  buffer exists. "Do profits cover it" = does equity stay >= $0 throughout.
//
//  Reuses lab-new4.js's exact strategy code + exit model. DATA-ONLY.
//  Run:  node power-hour-drawdown.js
// =============================================================
"use strict";

const fs = require("fs");
const Yahoo = require("./yahoo.js");
const Lab = require("./lab-new4.js");

const KEY = "powerHour";
const MLL = Lab.MLL, DLL = Lab.DLL;
const f = (x, d = 0) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));
const money = (x) => (x >= 0 ? "+$" : "-$") + f(Math.abs(x));
function etStr(s) {
  return new Date(s * 1000).toLocaleString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

(async () => {
  let bars = null;
  try { bars = await Yahoo.fetchBars({ interval: "5m", range: "60d" }); }
  catch (e) { console.error(`Yahoo live fetch failed (${e.message}); using cached data/nq-5m.json`); bars = JSON.parse(fs.readFileSync(__dirname + "/data/nq-5m.json", "utf8")); }

  const S = Lab.buildAll(bars);
  const ledger = Lab.runLedger(bars, S[KEY]);     // [{date, pts, entryT, exitT, dir}]

  // build equity curve in $ at both sizes; track running peak, drawdown, and
  // the single largest peak->trough slide.
  const PV5 = 10, PV1 = 2;
  let cum = 0, peak = 0, runPeakIdx = -1;     // running peak (in pts)
  let maxDD = 0, ddPeakIdx = -1, ddTroughIdx = -1;
  let minEquity = 0, minEquityIdx = -1;       // lowest cumulative equity ever (pts)
  const curve = [];
  for (let k = 0; k < ledger.length; k++) {
    cum += ledger[k].pts;
    if (cum > peak) { peak = cum; runPeakIdx = k; }
    const dd = peak - cum;
    if (dd > maxDD) { maxDD = dd; ddPeakIdx = runPeakIdx; ddTroughIdx = k; }
    if (cum < minEquity) { minEquity = cum; minEquityIdx = k; }
    curve.push({ cum, peak, dd });
  }
  const finalPts = cum;

  console.log(`POWER-HOUR (#42) DRAWDOWN FORENSICS — full 58-day Yahoo NQ=F 5m, ${ledger.length} trades.`);
  console.log(`Equity in $ at 5 MNQ ($${PV5}/pt) and 1 MNQ ($${PV1}/pt). Start = $0 baseline (profit above the $50k account).\n`);

  // --- the worst slide ---
  const peakPts = ddPeakIdx >= 0 ? curve[ddPeakIdx].cum : 0;
  const troughPts = ddTroughIdx >= 0 ? curve[ddTroughIdx].cum : 0;
  const peakTrade = ledger[ddPeakIdx], troughTrade = ledger[ddTroughIdx];
  console.log(`WORST PEAK->TROUGH SLIDE (the ~$1,800 drawdown):`);
  console.log(`  Peak   : after trade #${ddPeakIdx + 1}  on ${etStr(peakTrade.entryT)}  -> equity ${money(peakPts * PV5)} @5MNQ  (${money(peakPts * PV1)} @1MNQ)`);
  console.log(`  Trough : after trade #${ddTroughIdx + 1}  on ${etStr(troughTrade.entryT)}  -> equity ${money(troughPts * PV5)} @5MNQ  (${money(troughPts * PV1)} @1MNQ)`);
  console.log(`  Drawdown: ${money(-maxDD * PV5)} @5MNQ  (${money(-maxDD * PV1)} @1MNQ)   = ${f(maxDD * PV5 / MLL * 100)}% of the $${MLL} MLL at 5 MNQ`);

  // trades inside the slide
  console.log(`\n  Trades during the slide (#${ddPeakIdx + 2} .. #${ddTroughIdx + 1}):`);
  console.log(`  ${"#".padStart(4)}  ${"entry (ET)".padEnd(16)} ${"dir".padEnd(5)} ${"pts".padStart(8)} ${"$@5MNQ".padStart(9)} ${"runEquity@5".padStart(13)}`);
  for (let k = ddPeakIdx + 1; k <= ddTroughIdx; k++) {
    const t = ledger[k];
    console.log(`  ${String(k + 1).padStart(4)}  ${etStr(t.entryT).padEnd(16)} ${(t.dir === 1 ? "long" : "short").padEnd(5)} ${f(t.pts, 2).padStart(8)} ${money(t.pts * PV5).padStart(9)} ${money(curve[k].cum * PV5).padStart(13)}`);
  }

  // --- does profit cover it? ---
  console.log(`\nDOES PROFIT COVER IT?`);
  console.log(`  Lowest equity EVER reached: ${money(minEquity * PV5)} @5MNQ (${money(minEquity * PV1)} @1MNQ)${minEquityIdx >= 0 ? " on " + etStr(ledger[minEquityIdx].entryT) : ""}`);
  console.log(`  Final equity (whole sample): ${money(finalPts * PV5)} @5MNQ (${money(finalPts * PV1)} @1MNQ)`);
  const bufferBefore = peakPts; // profit banked before the slide began
  console.log(`  Profit banked BEFORE the slide began: ${money(bufferBefore * PV5)} @5MNQ`);
  if (minEquity >= 0) {
    console.log(`  YES — equity NEVER went below the starting balance. Every drawdown, including the worst, was absorbed by profit already banked. The account was never underwater.`);
  } else {
    console.log(`  WARNING — equity dipped ${money(minEquity * PV5)} below start at its worst; the cushion did NOT fully cover that slide at 5 MNQ.`);
  }
  // MLL check: trailing MLL only fails if a single peak->trough slide exceeds $2,000
  const mllSafe5 = maxDD * PV5 < MLL, mllSafe1 = maxDD * PV1 < MLL;
  console.log(`\n  Trailing-MLL survival (largest single slide vs $${MLL}):  5 MNQ = ${mllSafe5 ? "SAFE" : "FAIL"} (${money(-maxDD * PV5)})   1 MNQ = ${mllSafe1 ? "SAFE" : "FAIL"} (${money(-maxDD * PV1)})`);
  console.log(`  Note: the MLL trails the PEAK, so what matters is the worst single slide ($${f(maxDD * PV5)} @5MNQ), not total give-back. Worst slide stayed ${mllSafe5 ? "under" : "over"} the $${MLL} limit.`);
})().catch((e) => { console.error("power-hour-drawdown error:", e.stack || e.message); process.exit(1); });
