// test-best3-90d.js — detailed 90-day backtest of the 3 best tweaked methods,
// gross + net-of-cost, with Combine feasibility and +$3,000 target check.
"use strict";
const Lab = require("./lab-new4.js");
const G = require("./strat-gen.js");
const O = require("./optimize-strat.js");
const dol = x => (x >= 0 ? "+$" : "-$") + Math.abs(Math.round(x)).toLocaleString();

// ---- method helpers ----
const rng = (C, i) => C.h[i] - C.l[i] || 1e-9;
const topThird = (C, i) => (C.c[i] - C.l[i]) / rng(C, i) > 0.66;
const botThird = (C, i) => (C.h[i] - C.c[i]) / rng(C, i) > 0.66;
const trendUp = (C, i) => C.ema50[i] != null && C.c[i] > C.ema50[i];
const trendDn = (C, i) => C.ema50[i] != null && C.c[i] < C.ema50[i];
function keyRev(C, i) { let nl = true, nh = true; for (let q = 1; q <= 5; q++) { if (C.l[i] >= C.l[i - q]) nl = false; if (C.h[i] <= C.h[i - q]) nh = false; } if (nl && C.c[i] > C.o[i] && C.c[i] > C.c[i - 1]) return 1; if (nh && C.c[i] < C.o[i] && C.c[i] < C.c[i - 1]) return -1; return 0; }
function dojiBrk(C, i) { const a = C.atr[i]; if (a == null) return 0; if (Math.abs(C.c[i - 1] - C.o[i - 1]) > 0.15 * a) return 0; if (C.c[i] > C.h[i - 1]) return 1; if (C.c[i] < C.l[i - 1]) return -1; return 0; }
function cciZero(C, i) { if (C.cci[i] == null || C.cci[i - 1] == null || C.ema200[i] == null) return 0; if (C.cci[i - 1] < 0 && C.cci[i] >= 0 && C.c[i] > C.ema200[i]) return 1; if (C.cci[i - 1] > 0 && C.cci[i] <= 0 && C.c[i] < C.ema200[i]) return -1; return 0; }

const BEST3 = [
  { name: "Key reversal AT Bollinger band", fn: (C, i) => { const d = keyRev(C, i); if (!d || C.bbL[i] == null) return 0; return (d === 1 ? C.l[i] <= C.bbL[i] : C.h[i] >= C.bbU[i]) ? d : 0; }, p: { stopMult: 1.5, tgtMult: 2.0, riskCap: 300, maxTr: 3, dayStop: -500 } },
  { name: "Doji break + EMA50 trend", fn: (C, i) => { const d = dojiBrk(C, i); return d && (d === 1 ? trendUp(C, i) : trendDn(C, i)) ? d : 0; }, p: { stopMult: 1.5, tgtMult: 2.0, riskCap: 300, maxTr: 3, dayStop: -500 } },
  { name: "CCI zero + strong close", fn: (C, i) => { const d = cciZero(C, i); return d && (d === 1 ? topThird(C, i) : botThird(C, i)) ? d : 0; }, p: { stopMult: 1.0, tgtMult: 3.5, riskCap: 200, maxTr: 3, dayStop: -500 } },
];
const COSTS = [{ tag: "gross", fee: 0, slipTicks: 0 }, { tag: "fee+2tk slip", fee: 0.37, slipTicks: 2 }];

const bars = Lab.loadCsv("C:\\Users\\kaide\\Downloads\\CME_MINI_DL_MNQ1!, 5 (1).csv");
const days = new Set(bars.map(b => Lab.dayKeyOf(b.t))).size;
const span = [bars[0].t, bars[bars.length - 1].t].map(s => new Date(s * 1000).toISOString().slice(0, 10));
const C = G.buildContext(bars), E = O.etArrays(bars);
console.log(`90-day MNQ chart: ${bars.length} bars, ${days} days, ${span.join(" -> ")}  (@5 MNQ vol-sized, $50K Combine: target +$3,000, DLL $1,000, MLL $2,000)\n`);

for (const m of BEST3) {
  const cfg = `stop ${m.p.stopMult}xATR / target ${m.p.tgtMult}xATR · $${m.p.riskCap} risk cap · ${m.p.maxTr} trades/day · -$500 daily stop`;
  console.log(`### ${m.name}`);
  console.log(`    ${cfg}`);
  console.log("    scenario".padEnd(18) + "Trd  Win    PF      Net      MaxDD    WorstDay  Feasible  Hits +$3k?");
  for (const c of COSTS) {
    const R = O.simCombine(bars, C, E, m.fn, m.p, c);
    console.log("    " + c.tag.padEnd(14) + String(R.n).padStart(3) + " " + (R.win + "%").padStart(6) + " " + String(R.pf).padStart(5) +
      " " + dol(R.net$).padStart(9) + " " + ("-$" + R.maxDD$).padStart(8) + " " + ("-$" + R.worstDay$).padStart(8) + "    " +
      (R.feasible ? "yes" : "DD!").padEnd(8) + "  " + (R.net$ >= 3000 ? "YES" : "no"));
  }
  console.log("");
}
