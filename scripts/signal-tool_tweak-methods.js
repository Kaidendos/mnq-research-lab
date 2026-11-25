// =============================================================
//  tweak-methods.js — improve the ENTRY LOGIC of the strongest edges (not just
//  params). Builds tweaked variants of NR4, key-reversal, FVG, doji, CCI (add
//  trend / ADX / strong-close / volume / VWAP-confluence), optimizes each with
//  risk control, and scores on 90d + 58d + TopStep's recent 13 days.
//
//  Pick rule per method: best risk-controlled config that is feasible on 90d and
//  net-positive on ALL THREE samples; ranked with recent-13d weighted.
//  DATA-ONLY. Run:  node tweak-methods.js
// =============================================================
"use strict";
const path = require("path");
const fs = require("fs");
const Lab = require("./lab-new4.js");
const G = require("./strat-gen.js");
const O = require("./optimize-strat.js");
const PX = require("./projectx.js");
const dol = x => (x >= 0 ? "+$" : "-$") + Math.abs(Math.round(x)).toLocaleString();

// ---- helpers on the context ----
const rng = (C, i) => C.h[i] - C.l[i] || 1e-9;
const topThird = (C, i) => (C.c[i] - C.l[i]) / rng(C, i) > 0.66;
const botThird = (C, i) => (C.h[i] - C.c[i]) / rng(C, i) > 0.66;
const nrK = (C, i, k) => { for (let j = 1; j <= k - 1; j++) if (rng(C, i - 1) >= rng(C, i - 1 - j)) return false; return true; };
const volUp = (C, i) => C.volAvg[i] != null && (C.v[i] || 0) > 1.2 * C.volAvg[i];
const trendUp = (C, i) => C.ema50[i] != null && C.c[i] > C.ema50[i];
const trendDn = (C, i) => C.ema50[i] != null && C.c[i] < C.ema50[i];
const adxOk = (C, i) => C.adx[i] != null && C.adx[i] > 20;

// NR-break core: returns raw break dir off bar i-1's range (after a narrow bar)
function nrBreak(C, i, k) { if (!nrK(C, i, k)) return 0; if (C.c[i] > C.h[i - 1]) return 1; if (C.c[i] < C.l[i - 1]) return -1; return 0; }
// key-reversal core: new 5-bar extreme that reverses
function keyRev(C, i) { let nl = true, nh = true; for (let q = 1; q <= 5; q++) { if (C.l[i] >= C.l[i - q]) nl = false; if (C.h[i] <= C.h[i - q]) nh = false; } if (nl && C.c[i] > C.o[i] && C.c[i] > C.c[i - 1]) return 1; if (nh && C.c[i] < C.o[i] && C.c[i] < C.c[i - 1]) return -1; return 0; }
const fvg = G.ENTRIES.find(e => e[0] === "fvg_w6_g02")[3];
function dojiBrk(C, i) { const a = C.atr[i]; if (a == null) return 0; if (Math.abs(C.c[i - 1] - C.o[i - 1]) > 0.15 * a) return 0; if (C.c[i] > C.h[i - 1]) return 1; if (C.c[i] < C.l[i - 1]) return -1; return 0; }
function cciZero(C, i) { if (C.cci[i] == null || C.cci[i - 1] == null || C.ema200[i] == null) return 0; if (C.cci[i - 1] < 0 && C.cci[i] >= 0 && C.c[i] > C.ema200[i]) return 1; if (C.cci[i - 1] > 0 && C.cci[i] <= 0 && C.c[i] < C.ema200[i]) return -1; return 0; }
const strongClose = (C, i, d) => d === 1 ? topThird(C, i) : botThird(C, i);
const vwapSide = (C, i, d) => C.vwap[i] != null && (d === 1 ? C.c[i] > C.vwap[i] : C.c[i] < C.vwap[i]);

// ---- tweaked METHODS: each fn(C,i) -> -1|0|1 ----
const METHODS = [
  // NR4 family (recent standout) — try to keep its edge while cutting drawdown
  ["nr4_base", "NR4 break (base)", (C, i) => nrBreak(C, i, 4)],
  ["nr4_trend", "NR4 break + EMA50 trend", (C, i) => { const d = nrBreak(C, i, 4); return d && (d === 1 ? trendUp(C, i) : trendDn(C, i)) ? d : 0; }],
  ["nr4_adx", "NR4 break + ADX>20", (C, i) => { const d = nrBreak(C, i, 4); return d && adxOk(C, i) ? d : 0; }],
  ["nr4_strong", "NR4 break + strong close", (C, i) => { const d = nrBreak(C, i, 4); return d && strongClose(C, i, d) ? d : 0; }],
  ["nr4_vol", "NR4 break + volume thrust", (C, i) => { const d = nrBreak(C, i, 4); return d && volUp(C, i) ? d : 0; }],
  ["nr4_vwap", "NR4 break + VWAP side", (C, i) => { const d = nrBreak(C, i, 4); return d && vwapSide(C, i, d) ? d : 0; }],
  ["nr4_trend_strong", "NR4 + trend + strong close", (C, i) => { const d = nrBreak(C, i, 4); return d && (d === 1 ? trendUp(C, i) : trendDn(C, i)) && strongClose(C, i, d) ? d : 0; }],
  ["nr7_trend", "NR7 break + EMA50 trend", (C, i) => { const d = nrBreak(C, i, 7); return d && (d === 1 ? trendUp(C, i) : trendDn(C, i)) ? d : 0; }],
  // key-reversal family
  ["key_base", "Key reversal (base)", (C, i) => keyRev(C, i)],
  ["key_vwap", "Key reversal at VWAP side", (C, i) => { const d = keyRev(C, i); return d && (d === 1 ? C.l[i] <= C.vwap[i] : C.h[i] >= C.vwap[i]) ? d : 0; }],
  ["key_adx", "Key reversal + ADX>20", (C, i) => { const d = keyRev(C, i); return d && adxOk(C, i) ? d : 0; }],
  ["key_bb", "Key reversal at BB band", (C, i) => { const d = keyRev(C, i); if (!d || C.bbL[i] == null) return 0; return (d === 1 ? C.l[i] <= C.bbL[i] : C.h[i] >= C.bbU[i]) ? d : 0; }],
  // FVG tweaks (try to rescue the laggard)
  ["fvg_strong", "FVG retest + strong close", (C, i) => { const d = fvg(C, i); return d && strongClose(C, i, d) ? d : 0; }],
  ["fvg_vol", "FVG retest + volume", (C, i) => { const d = fvg(C, i); return d && volUp(C, i) ? d : 0; }],
  // doji / cci tweaks
  ["doji_trend", "Doji break + EMA50 trend", (C, i) => { const d = dojiBrk(C, i); return d && (d === 1 ? trendUp(C, i) : trendDn(C, i)) ? d : 0; }],
  ["cci_strong", "CCI zero + strong close", (C, i) => { const d = cciZero(C, i); return d && strongClose(C, i, d) ? d : 0; }],
];

// ---- param grid for the risk-control overlay ----
const STOPS = [0.7, 1.0, 1.5], TGTS = [2.0, 2.5, 3.5], CAPS = [200, 300], MAXTR = [2, 3], DAYSTOP = -500;

function ctxPlus(bars) {
  const C = G.buildContext(bars);
  const v = C.v, volAvg = new Array(v.length).fill(null);
  for (let i = 19; i < v.length; i++) { let s = 0; for (let k = i - 19; k <= i; k++) s += v[k] || 0; volAvg[i] = s / 20; }
  C.volAvg = volAvg;
  return C;
}

(async () => {
  const bars90 = Lab.loadCsv("C:\\Users\\kaide\\Downloads\\CME_MINI_DL_MNQ1!, 5 (1).csv");
  const bars58 = JSON.parse(fs.readFileSync(path.join(__dirname, "data", "nq-5m.json"), "utf8")).filter(b => b && isFinite(b.c)).sort((a, b) => a.t - b.t);
  const barsTS = (await PX.fetchBars({ unitNumber: 5, lookbackDays: 25, contract: "MNQ", live: false })).filter(b => b && isFinite(b.c)).sort((a, b) => a.t - b.t);
  const rthDays = [...new Set(barsTS.filter(b => { const e = Lab.etParts(b.t); return e.day !== 0 && e.day !== 6 && e.mins >= 570 && e.mins < 960; }).map(b => Lab.dayKeyOf(b.t)))];
  const last13 = rthDays.slice(-13), cutoffT = barsTS.find(b => Lab.dayKeyOf(b.t) === last13[0]).t;
  const C90 = ctxPlus(bars90), C58 = ctxPlus(bars58), CTS = ctxPlus(barsTS);
  const E90 = O.etArrays(bars90), E58 = O.etArrays(bars58), ETS = O.etArrays(barsTS);
  console.log(`90d=${bars90.length}b  58d=${bars58.length}b  recent13d=${last13.length} days (${[cutoffT, barsTS[barsTS.length - 1].t].map(s => new Date(s * 1000).toISOString().slice(0, 10)).join("->")})\n`);

  const rows = METHODS.map(([key, name, fn]) => {
    let best = null;
    for (const stopMult of STOPS) for (const tgtMult of TGTS) for (const riskCap of CAPS) for (const maxTr of MAXTR) {
      const p = { stopMult, tgtMult, riskCap, maxTr, dayStop: DAYSTOP };
      const R90 = O.simCombine(bars90, C90, E90, fn, p);
      if (!R90.feasible || R90.net$ <= 0 || R90.n < 20) continue;
      const R58 = O.simCombine(bars58, C58, E58, fn, p);
      const gated = (C2, i) => (barsTS[i].t >= cutoffT ? fn(C2, i) : 0);
      const R13 = O.simCombine(barsTS, CTS, ETS, gated, p);
      // robust score: reward consistency, weight recent-13d
      const score = (R90.net$ + R58.net$) / 2 + R13.net$ * 2 + (R58.net$ > 0 ? 1500 : 0) + (R13.net$ > 0 ? 1500 : 0);
      if (!best || score > best.score) best = { key, name, p, R90, R58, R13, score };
    }
    return best || { key, name, none: true };
  }).filter(r => !r.none).sort((a, b) => b.score - a.score);

  console.log("METHOD (best risk-controlled config)".padEnd(34) + "cfg".padEnd(16) + "| 90d net  win  | 58d net  | 13d net  win  | all+?");
  for (const r of rows) {
    const cfg = `s${r.p.stopMult}/t${r.p.tgtMult} $${r.p.riskCap} ${r.p.maxTr}/d`;
    const allPos = r.R90.net$ > 0 && r.R58.net$ > 0 && r.R13.net$ > 0;
    console.log(r.name.slice(0, 33).padEnd(34) + cfg.padEnd(16) + "| " + dol(r.R90.net$).padStart(7) + " " + (r.R90.win + "%").padStart(5) +
      " | " + dol(r.R58.net$).padStart(7) + " | " + dol(r.R13.net$).padStart(7) + " " + (r.R13.win + "%").padStart(5) + " | " + (allPos ? "✅" : ""));
  }
})().catch(e => console.log("ERR", e.message, e.stack));
