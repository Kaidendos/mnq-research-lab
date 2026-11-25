// backtest-topstep13.js — backtest the optimized FVG configs on TopStep's most
// recent 13 trading days (live ProjectX feed, sim subscription), with full
// indicator warmup from earlier bars. Frictionless + net-of-cost.
"use strict";
const Lab = require("./lab-new4.js");
const G = require("./strat-gen.js");
const O = require("./optimize-strat.js");
const PX = require("./projectx.js");
const dol = x => (x >= 0 ? "+$" : "-$") + Math.abs(Math.round(x)).toLocaleString();

const fvg = G.ENTRIES.find(e => e[0] === "fvg_w6_g02")[3];
const fvgTrend = G.ENTRIES.find(e => e[0] === "fvg_trend")[3];
const CONFIGS = [
  { name: "WINNER: FVG g.2ATR [adx] s1.5/t3.5 $200 3/d", fn: O.withFilter(fvg, "adx"), p: { stopMult: 1.5, tgtMult: 3.5, riskCap: 200, maxTr: 3, dayStop: -500 } },
  { name: "FVG+EMA50 [adx] s1.5/t3.5 $200 3/d",          fn: O.withFilter(fvgTrend, "adx"), p: { stopMult: 1.5, tgtMult: 3.5, riskCap: 200, maxTr: 3, dayStop: -500 } },
  { name: "FVG g.2ATR [adx] s1.5/t2.5 $300 2/d",         fn: O.withFilter(fvg, "adx"), p: { stopMult: 1.5, tgtMult: 2.5, riskCap: 300, maxTr: 2, dayStop: -500 } },
];
const COSTS = [{ tag: "gross", fee: 0, slipTicks: 0 }, { tag: "fee+2tk slip", fee: 0.37, slipTicks: 2 }];

(async () => {
  const bars = (await PX.fetchBars({ unitNumber: 5, lookbackDays: 25, contract: "MNQ", live: false }))
    .filter(b => b && isFinite(b.c)).sort((a, b) => a.t - b.t);
  const rthDays = [...new Set(bars.filter(b => { const e = Lab.etParts(b.t); return e.day !== 0 && e.day !== 6 && e.mins >= 570 && e.mins < 960; }).map(b => Lab.dayKeyOf(b.t)))];
  const last13 = rthDays.slice(-13);
  const cutoffT = bars.find(b => Lab.dayKeyOf(b.t) === last13[0]).t;
  const span = [cutoffT, bars[bars.length - 1].t].map(s => new Date(s * 1000).toISOString().slice(0, 10));
  console.log(`TopStep feed: ${bars.length} bars total; warmup before cutoff, trading on the last ${last13.length} RTH days.`);
  console.log(`13-day window: ${span.join(" -> ")}  (entries only on/after ${last13[0]})\n`);

  const C = G.buildContext(bars), E = O.etArrays(bars);
  for (const cf of CONFIGS) {
    const gated = (C2, i) => (bars[i].t >= cutoffT ? cf.fn(C2, i) : 0); // warmup-only before cutoff
    console.log(`### ${cf.name}`);
    console.log("  scenario".padEnd(16) + "Trd  Win    PF      Net      MaxDD   WorstDay  Feasible");
    for (const c of COSTS) {
      const R = O.simCombine(bars, C, E, gated, cf.p, c);
      console.log("  " + c.tag.padEnd(14) + String(R.n).padStart(3) + " " + (R.win + "%").padStart(6) + " " + String(R.pf).padStart(5) +
        " " + dol(R.net$).padStart(8) + " " + ("-$" + R.maxDD$).padStart(8) + " " + ("-$" + R.worstDay$).padStart(8) + "   " + (R.feasible ? "yes" : "DD!"));
    }
    console.log("");
  }
})().catch(e => console.log("ERR", e.message, e.stack));
