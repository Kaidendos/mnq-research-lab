// stress-fvg.js — run the recommended optimized config through fees + slippage
// on all three datasets to see the REALISTIC (net-of-cost) result.
//   winner: FVG retest (win6, gap.2ATR) + ADX>20 filter, stop 1.5xATR / target
//           3.5xATR, $200 risk cap, 3 trades/day, -$500 daily stop.
"use strict";
const path = require("path");
const fs = require("fs");
const Lab = require("./lab-new4.js");
const G = require("./strat-gen.js");
const O = require("./optimize-strat.js");

const dol = x => (x >= 0 ? "+$" : "-$") + Math.abs(Math.round(x)).toLocaleString();
const baseFn = G.ENTRIES.find(e => e[0] === "fvg_w6_g02")[3];
const dirFn = O.withFilter(baseFn, "adx");
const p = { stopMult: 1.5, tgtMult: 3.5, riskCap: 200, maxTr: 3, dayStop: -500 };

const CSV_90 = "C:\\Users\\kaide\\Downloads\\CME_MINI_DL_MNQ1!, 5 (1).csv";
const loadJson = f => JSON.parse(fs.readFileSync(f, "utf8")).filter(b => b && isFinite(b.c)).sort((a, b) => a.t - b.t);
const sets = [
  { tag: "90d", bars: Lab.loadCsv(CSV_90) },
  { tag: "58d", bars: loadJson(path.join(__dirname, "data", "nq-5m.json")) },
];
try { sets.push({ tag: "13d", bars: Lab.loadCsv(Lab.CSV_13) }); } catch {}

// cost scenarios: MNQ commission ~$0.37/side/contract; slippage in ticks on entry+stop
const COSTS = [
  { tag: "frictionless", fee: 0, slipTicks: 0 },
  { tag: "fee only", fee: 0.37, slipTicks: 0 },
  { tag: "fee + 1tk slip", fee: 0.37, slipTicks: 1 },
  { tag: "fee + 2tk slip", fee: 0.37, slipTicks: 2 },
];

console.log("Winner: FVG retest (g.2ATR) + ADX>20 · s1.5/t3.5 · $200 cap · 3/day · -$500 dayStop\n");
for (const s of sets) {
  const C = G.buildContext(s.bars), E = O.etArrays(s.bars);
  const days = new Set(s.bars.map(b => Lab.dayKeyOf(b.t))).size;
  console.log(`===== ${s.tag} (${days} days) =====`);
  console.log("scenario".padEnd(16) + "Trd  Win    PF     Net      Fees     MaxDD    WorstDay  Feasible");
  for (const c of COSTS) {
    const R = O.simCombine(s.bars, C, E, dirFn, p, c);
    console.log(c.tag.padEnd(16) + String(R.n).padStart(3) + " " + (R.win + "%").padStart(5) + " " +
      String(R.pf).padStart(5) + " " + dol(R.net$).padStart(8) + " " + ("-$" + R.fees$).padStart(8) + " " +
      ("-$" + R.maxDD$).padStart(8) + " " + ("-$" + R.worstDay$).padStart(8) + "   " + (R.feasible ? "yes" : "DD!"));
  }
  console.log("");
}
