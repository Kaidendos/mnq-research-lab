// strat-battle-13d.js - Generation 2 strategy search
// Lessons encoded: risk-control first, reversal-at-level only, net of costs,
// feasibility as a hard gate, MC validation on survivors.
// Run: node strat-battle-13d.js
"use strict";

const fs   = require("fs");
const path = require("path");
require("./public/indicators.js");
const I = globalThis.Indicators;

const PV     = 2;      // $/pt @ 1 MNQ
const MAXC   = 5;
const DLL    = 1000;   // TopStep daily loss limit
const MLL    = 2000;   // TopStep max trailing drawdown
const TARGET = 3000;   // $50K Combine profit target
const TICK   = 0.25;
const FEE    = 0.37;   // per side per contract
const SLIP   = 2;      // ticks slippage each side
const RTH_S  = 570;    // 9:30 ET in minutes
const RTH_E  = 960;    // 16:00 ET

// ---- fast ET computation (no locale API per bar) ----
function etPartsFromEpoch(s) {
  const utcMs = s * 1000;
  const d = new Date(utcMs);
  const y = d.getUTCFullYear();
  // Second Sunday in March (DST start)
  const ms = new Date(Date.UTC(y, 2, 1));
  ms.setUTCDate(1 + ((7 - ms.getUTCDay()) % 7) + 7);
  // First Sunday in November (DST end)
  const ns = new Date(Date.UTC(y, 10, 1));
  ns.setUTCDate(1 + ((7 - ns.getUTCDay()) % 7));
  const off = (utcMs >= ms.getTime() && utcMs < ns.getTime()) ? -240 : -300;
  const et  = new Date(utcMs + off * 60000);
  const day = et.getUTCDay();
  const mins = et.getUTCHours() * 60 + et.getUTCMinutes();
  const k = et.getUTCFullYear() + "-" +
    String(et.getUTCMonth() + 1).padStart(2, "0") + "-" +
    String(et.getUTCDate()).padStart(2, "0");
  return { day, mins, k };
}

function precomputeET(bars) {
  const n = bars.length;
  const dayKey = new Array(n);
  const inRTH  = new Array(n);
  const dayMin  = new Array(n);
  const dotw    = new Array(n);
  for (let i = 0; i < n; i++) {
    const p = etPartsFromEpoch(bars[i].t);
    dayKey[i] = p.k;
    dotw[i]   = p.day;
    dayMin[i] = p.mins;
    inRTH[i]  = p.day >= 1 && p.day <= 5 && p.mins >= RTH_S && p.mins < RTH_E;
  }
  return { dayKey, inRTH, dayMin, dotw };
}

// ---- build all indicators once ----
function buildCtx(bars, ET) {
  const n  = bars.length;
  const o  = bars.map(b => b.o);
  const h  = bars.map(b => b.h);
  const l  = bars.map(b => b.l);
  const c  = bars.map(b => b.c);
  const v  = bars.map(b => b.v || 0);

  const ema21  = I.ema(c, 21);
  const ema200 = I.ema(c, 200);
  const atr    = I.atr(h, l, c, 14);
  const rsi14  = I.rsi(c, 14);
  const rsi2   = I.rsi(c, 2);

  const bbBasis = I.sma(c, 20);
  const bbStd   = I.stdev(c, 20);
  const bbU = bbBasis.map((v2, i) => v2 == null ? null : v2 + 2 * bbStd[i]);
  const bbL = bbBasis.map((v2, i) => v2 == null ? null : v2 - 2 * bbStd[i]);

  const ema20 = I.ema(c, 20);
  const keltU = ema20.map((v2, i) => v2 == null || atr[i] == null ? null : v2 + 1.5 * atr[i]);
  const keltL = ema20.map((v2, i) => v2 == null || atr[i] == null ? null : v2 - 1.5 * atr[i]);

  // Stochastic K raw
  const sRaw = new Array(n).fill(null);
  for (let i = 13; i < n; i++) {
    let hh = -Infinity, ll = Infinity;
    for (let k = i - 13; k <= i; k++) { hh = Math.max(hh, h[k]); ll = Math.min(ll, l[k]); }
    sRaw[i] = hh > ll ? (c[i] - ll) / (hh - ll) * 100 : 50;
  }
  const sKsrc = sRaw.map(x => x == null ? 0 : x);
  const stochK = I.sma(sKsrc, 3).map((v2, i) => sRaw[i] == null ? null : v2);

  const volAvg = I.sma(v, 20);

  // Session VWAP with sigma
  const vwap   = new Array(n).fill(null);
  const vwapSd = new Array(n).fill(null);
  let vN = 0, vD = 0, vN2 = 0, curDay = null;
  for (let i = 0; i < n; i++) {
    const dk = ET.dayKey[i], inR = ET.inRTH[i];
    if (dk !== curDay) { vN = vD = vN2 = 0; curDay = dk; }
    if (inR) {
      const hlc3 = (h[i] + l[i] + c[i]) / 3, vol = v[i] || 1;
      vN += hlc3 * vol; vN2 += hlc3 * hlc3 * vol; vD += vol;
      if (vD > 0) {
        const m = vN / vD;
        vwap[i]   = m;
        vwapSd[i] = Math.sqrt(Math.max(0, vN2 / vD - m * m));
      }
    }
  }

  // Opening range H/L (first 30 min = RTH_S to RTH_S+30)
  const orH = new Array(n).fill(null);
  const orL = new Array(n).fill(null);
  let oRH = -Infinity, oRL = Infinity, oRday = null;
  for (let i = 0; i < n; i++) {
    const dk = ET.dayKey[i], mins = ET.dayMin[i], dow = ET.dotw[i];
    if (dk !== oRday) { oRH = -Infinity; oRL = Infinity; oRday = dk; }
    if (dow >= 1 && dow <= 5 && mins >= RTH_S && mins < RTH_S + 30) {
      oRH = Math.max(oRH, h[i]); oRL = Math.min(oRL, l[i]);
    }
    orH[i] = oRH === -Infinity ? null : oRH;
    orL[i] = oRL === Infinity  ? null : oRL;
  }

  // 3-bar consecutive close direction (prior 3 bars before this one)
  const c3Dn = new Array(n).fill(false);
  const c3Up = new Array(n).fill(false);
  for (let i = 3; i < n; i++) {
    c3Dn[i] = c[i-1] < c[i-2] && c[i-2] < c[i-3];
    c3Up[i] = c[i-1] > c[i-2] && c[i-2] > c[i-3];
  }

  return { o, h, l, c, v, n,
    ema21, ema200, atr, rsi14, rsi2,
    bbBasis, bbU, bbL, keltU, keltL,
    stochK, volAvg, vwap, vwapSd,
    orH, orL, c3Dn, c3Up };
}

// ---- helper: key-reversal bar (5-bar new extreme + bullish/bearish body) ----
function keyRevDir(C, i) {
  if (i < 5) return 0;
  let nl = true, nh = true;
  for (let q = 1; q <= 5; q++) {
    if (C.l[i] >= C.l[i-q]) nl = false;
    if (C.h[i] <= C.h[i-q]) nh = false;
  }
  if (nl && C.c[i] > C.o[i] && C.c[i] > C.c[i-1]) return  1;
  if (nh && C.c[i] < C.o[i] && C.c[i] < C.c[i-1]) return -1;
  return 0;
}

// ---- risk-controlled sim ----
function simWithRisk(bars, C, ET, dirFn, p) {
  const slip = (p.slipTicks || 0) * TICK;
  const fee  = p.fee || 0;
  let equity = 0, peak = 0, maxDD = 0, wins = 0, gW = 0, gL = 0;
  const trades = [];
  const byDay  = new Map();
  let pos = null, dayState = { k: null, real: 0, tr: 0 };
  let i = 210; // indicator warmup

  while (i < bars.length) {
    const b   = bars[i];
    const dk  = ET.dayKey[i];
    const inR = ET.inRTH[i];
    if (dk !== dayState.k) dayState = { k: dk, real: 0, tr: 0 };

    if (pos) {
      const long = pos.dir === 1;
      let px = null;
      if (dk !== pos.day || !inR) {
        px = long ? bars[i-1].c - slip : bars[i-1].c + slip; // force flat
      } else if (long ? b.l <= pos.stop : b.h >= pos.stop) {
        px = long ? pos.stop - slip : pos.stop + slip;
      } else if (long ? b.h >= pos.target : b.l <= pos.target) {
        px = pos.target;
      }
      if (px != null) {
        const pts = long ? px - pos.entry : pos.entry - px;
        const pnl = pts * pos.size * PV - 2 * pos.size * fee;
        equity += pnl;
        peak    = Math.max(peak, equity);
        maxDD   = Math.max(maxDD, peak - equity);
        dayState.real += pnl;
        byDay.set(dk, (byDay.get(dk) || 0) + pnl);
        if (pnl > 0) { wins++; gW += pnl; } else gL += Math.abs(pnl);
        trades.push({ pnl, day: dk, dir: pos.dir, pts });
        pos = null; i++; continue;
      }
    }

    if (!pos && inR && dayState.real > p.dayStop && dayState.tr < p.maxTr) {
      const a = C.atr[i];
      let d = 0;
      try { d = dirFn(C, i) || 0; } catch (_) {}
      if (d && a != null && a > 0) {
        const stopPts = p.stopMult * a;
        const size    = Math.max(1, Math.min(MAXC, Math.floor(p.riskCap / (stopPts * PV))));
        const fill    = d === 1 ? C.c[i] + slip : C.c[i] - slip;
        pos = {
          dir: d, entry: fill, size, day: dk,
          stop:   d === 1 ? fill - stopPts : fill + stopPts,
          target: d === 1 ? fill + p.tgtMult * a : fill - p.tgtMult * a,
        };
        dayState.tr++;
      }
    }
    i++;
  }

  const n2 = trades.length;
  const wdVals = byDay.size ? [...byDay.values()] : [0];
  const worstDay = -Math.min(0, ...wdVals);
  return {
    n: n2,
    win:  n2 ? +(wins / n2 * 100).toFixed(1) : 0,
    pf:   gL > 0 ? +(gW / gL).toFixed(2) : (gW > 0 ? 99 : 0),
    net$: Math.round(equity),
    maxDD$: Math.round(maxDD),
    worstDay$: Math.round(worstDay),
    feasible: maxDD < MLL && worstDay < DLL,
    trades, byDay,
  };
}

// Chronological Combine pass: reach +TARGET before -MLL trailing DD or -DLL day
function combinePass(trades) {
  let cum = 0, peak = 0;
  const bd = new Map();
  for (const t of trades) {
    cum += t.pnl; peak = Math.max(peak, cum);
    bd.set(t.day, (bd.get(t.day) || 0) + t.pnl);
    if (peak - cum >= MLL)        return { passed: false, why: "MLL" };
    if (bd.get(t.day) <= -DLL)    return { passed: false, why: "DLL" };
    if (cum >= TARGET)             return { passed: true,  why: "target" };
  }
  return { passed: false, why: "no-target" };
}

// Monte-Carlo: shuffle trade order, % that reach +TARGET before -MLL trailing DD
function mcPass(trades, iters) {
  iters = iters || 2000;
  if (!trades.length) return 0;
  const pnls = trades.map(t => t.pnl);
  let pass = 0;
  for (let it = 0; it < iters; it++) {
    for (let k = pnls.length - 1; k > 0; k--) {
      const j = (Math.random() * (k + 1)) | 0;
      const tmp = pnls[k]; pnls[k] = pnls[j]; pnls[j] = tmp;
    }
    let cum = 0, peak = 0, ok = false, dead = false;
    for (let k = 0; k < pnls.length; k++) {
      cum += pnls[k]; peak = Math.max(peak, cum);
      if (peak - cum >= MLL) { dead = true; break; }
      if (cum >= TARGET)     { ok   = true; break; }
    }
    if (ok && !dead) pass++;
  }
  return +(pass / iters * 100).toFixed(1);
}

// ---- entry methods ----
const METHODS = [

  // BENCHMARK: current champion
  ["BENCH: KeyRev@BB+Reclaim", function(C, i) {
    const d = keyRevDir(C, i);
    if (!d || C.bbU[i] == null) return 0;
    if (d ===  1 && C.l[i] <= C.bbL[i] && C.c[i] > C.bbL[i]) return  1;
    if (d === -1 && C.h[i] >= C.bbU[i] && C.c[i] < C.bbU[i]) return -1;
    return 0;
  }],

  // S1: KeyRev@BB + VWAP session bias
  ["S1: KeyRev@BB + VWAP bias", function(C, i) {
    const d = keyRevDir(C, i);
    if (!d || C.bbU[i] == null || C.vwap[i] == null) return 0;
    if (d ===  1 && C.l[i] <= C.bbL[i] && C.c[i] > C.bbL[i] && C.c[i] < C.vwap[i]) return  1;
    if (d === -1 && C.h[i] >= C.bbU[i] && C.c[i] < C.bbU[i] && C.c[i] > C.vwap[i]) return -1;
    return 0;
  }],

  // S2: KeyRev@BB + 3-bar exhaustion leading into it
  ["S2: KeyRev@BB + 3-bar exhaust", function(C, i) {
    const d = keyRevDir(C, i);
    if (!d || C.bbU[i] == null) return 0;
    if (d ===  1 && C.l[i] <= C.bbL[i] && C.c[i] > C.bbL[i] && C.c3Dn[i]) return  1;
    if (d === -1 && C.h[i] >= C.bbU[i] && C.c[i] < C.bbU[i] && C.c3Up[i]) return -1;
    return 0;
  }],

  // S3: KeyRev@BB + Stochastic extreme
  ["S3: KeyRev@BB + Stoch extreme", function(C, i) {
    const d = keyRevDir(C, i);
    if (!d || C.bbU[i] == null || C.stochK[i] == null) return 0;
    if (d ===  1 && C.l[i] <= C.bbL[i] && C.c[i] > C.bbL[i] && C.stochK[i] < 20) return  1;
    if (d === -1 && C.h[i] >= C.bbU[i] && C.c[i] < C.bbU[i] && C.stochK[i] > 80) return -1;
    return 0;
  }],

  // S4: RSI2 extreme + BB pierce + strong body (triple confluence)
  ["S4: RSI2 extreme + BB + body", function(C, i) {
    if (C.bbU[i] == null || C.rsi2[i] == null || C.atr[i] == null) return 0;
    const rng = C.h[i] - C.l[i];
    if (rng < 0.001) return 0;
    const topThird = (C.c[i] - C.l[i]) / rng > 0.66;
    const botThird = (C.h[i] - C.c[i]) / rng > 0.66;
    if (C.l[i] <= C.bbL[i] && C.c[i] > C.bbL[i] && C.rsi2[i] < 5  && topThird) return  1;
    if (C.h[i] >= C.bbU[i] && C.c[i] < C.bbU[i] && C.rsi2[i] > 95 && botThird) return -1;
    return 0;
  }],

  // S5: VWAP rubber-band fade (>2 sigma from VWAP + new 5-bar extreme)
  ["S5: VWAP rubber-band fade", function(C, i) {
    if (i < 5) return 0;
    if (C.vwap[i] == null || C.vwapSd[i] == null || C.vwapSd[i] < 0.01) return 0;
    const vw = C.vwap[i], sd = C.vwapSd[i];
    let nl = true, nh = true;
    for (let q = 1; q <= 5; q++) {
      if (C.l[i] >= C.l[i-q]) nl = false;
      if (C.h[i] <= C.h[i-q]) nh = false;
    }
    if (nl && C.c[i] < vw - 2 * sd && C.c[i] > C.c[i-1]) return  1;
    if (nh && C.c[i] > vw + 2 * sd && C.c[i] < C.c[i-1]) return -1;
    return 0;
  }],

  // S6: Opening-range false-break fade
  ["S6: OR false-break fade", function(C, i) {
    if (i < 5) return 0;
    if (C.orH[i] == null || C.atr[i] == null) return 0;
    if (C.orH[i] - C.orL[i] < 1) return 0; // OR not established
    const d = keyRevDir(C, i);
    if (!d) return 0;
    if (d ===  1 && C.l[i] < C.orL[i] && C.c[i] >= C.orL[i]) return  1;
    if (d === -1 && C.h[i] > C.orH[i] && C.c[i] <= C.orH[i]) return -1;
    return 0;
  }],

  // S7: EMA21 pullback in EMA200 trend direction
  ["S7: EMA21 pullback + trend", function(C, i) {
    if (i < 5) return 0;
    if (C.ema21[i] == null || C.ema200[i] == null) return 0;
    const d = keyRevDir(C, i);
    if (!d) return 0;
    const upTrend = C.c[i] > C.ema200[i];
    const dnTrend = C.c[i] < C.ema200[i];
    if (d ===  1 && upTrend && C.l[i] <= C.ema21[i] && C.c[i] > C.ema21[i]) return  1;
    if (d === -1 && dnTrend && C.h[i] >= C.ema21[i] && C.c[i] < C.ema21[i]) return -1;
    return 0;
  }],

  // S8: BB-squeeze (BB inside Keltner) + band pierce fade
  ["S8: BB squeeze band-fade", function(C, i) {
    if (i < 5) return 0;
    if (C.bbU[i] == null || C.keltU[i] == null) return 0;
    if (!(C.bbU[i] < C.keltU[i] && C.bbL[i] > C.keltL[i])) return 0; // no squeeze
    const d = keyRevDir(C, i);
    if (!d) return 0;
    if (d ===  1 && C.l[i] <= C.bbL[i] && C.c[i] > C.bbL[i]) return  1;
    if (d === -1 && C.h[i] >= C.bbU[i] && C.c[i] < C.bbU[i]) return -1;
    return 0;
  }],

  // S9: RSI14 midline cross at BB extreme
  ["S9: RSI14 midline cross + BB", function(C, i) {
    if (i < 2) return 0;
    if (C.bbU[i] == null || C.rsi14[i] == null || C.atr[i] == null) return 0;
    const crossUp = C.rsi14[i-1] < 50 && C.rsi14[i] >= 50;
    const crossDn = C.rsi14[i-1] > 50 && C.rsi14[i] <= 50;
    const nearL   = C.c[i] < C.bbL[i] + C.atr[i];
    const nearU   = C.c[i] > C.bbU[i] - C.atr[i];
    if (crossUp && nearL) return  1;
    if (crossDn && nearU) return -1;
    return 0;
  }],

  // S10: KeyRev@BB + high-volume thrust (1.5x avg)
  ["S10: KeyRev@BB + vol thrust", function(C, i) {
    const d = keyRevDir(C, i);
    if (!d || C.bbU[i] == null || C.volAvg[i] == null) return 0;
    if (!((C.v[i] || 0) > 1.5 * C.volAvg[i])) return 0;
    if (d ===  1 && C.l[i] <= C.bbL[i] && C.c[i] > C.bbL[i]) return  1;
    if (d === -1 && C.h[i] >= C.bbU[i] && C.c[i] < C.bbU[i]) return -1;
    return 0;
  }],

];

// ---- risk config grid (anchored around proven champion params) ----
const CONFIGS = [
  { stopMult: 1.5, tgtMult: 2.0, riskCap: 200, maxTr: 2, dayStop: -700, fee: FEE, slipTicks: SLIP },
  { stopMult: 1.5, tgtMult: 2.0, riskCap: 200, maxTr: 2, dayStop: -500, fee: FEE, slipTicks: SLIP },
  { stopMult: 1.2, tgtMult: 2.0, riskCap: 200, maxTr: 2, dayStop: -700, fee: FEE, slipTicks: SLIP },
  { stopMult: 1.5, tgtMult: 2.5, riskCap: 200, maxTr: 2, dayStop: -700, fee: FEE, slipTicks: SLIP },
  { stopMult: 1.5, tgtMult: 2.0, riskCap: 200, maxTr: 3, dayStop: -700, fee: FEE, slipTicks: SLIP },
];

const dol = function(x) { return (x >= 0 ? "+$" : "-$") + Math.abs(Math.round(x)).toLocaleString(); };
const pct = function(x) { return x.toFixed(1) + "%"; };

// ---- main ----
(function main() {
  console.log("Loading data...");
  const dataPath = path.join(__dirname, "data", "nq-5m.json");
  const allBars = JSON.parse(fs.readFileSync(dataPath, "utf8"))
    .filter(function(b) { return b && isFinite(b.c); })
    .sort(function(a, b) { return a.t - b.t; });

  const first = new Date(allBars[0].t * 1000).toISOString().slice(0, 10);
  const last  = new Date(allBars[allBars.length - 1].t * 1000).toISOString().slice(0, 10);
  console.log("Full dataset: " + allBars.length + " bars  (" + first + " to " + last + ")");

  console.log("Pre-computing ET timestamps...");
  const ET = precomputeET(allBars);

  // RTH trading days
  const daySet = new Set();
  for (let i = 0; i < allBars.length; i++) {
    if (ET.inRTH[i]) daySet.add(ET.dayKey[i]);
  }
  const rthDays = Array.from(daySet).sort();
  const last13  = rthDays.slice(-13);
  const cutoffT = (function() {
    for (let i = 0; i < allBars.length; i++) {
      if (ET.dayKey[i] === last13[0]) return allBars[i].t;
    }
    return Infinity;
  })();

  console.log("RTH days in dataset: " + rthDays.length);
  console.log("13d window: " + last13[0] + " to " + last13[last13.length - 1]);
  console.log("Building indicators...");
  const C = buildCtx(allBars, ET);

  function run13(dirFn, p) {
    return simWithRisk(allBars, C, ET,
      function(C2, i) { return allBars[i].t >= cutoffT ? dirFn(C2, i) : 0; }, p);
  }
  function runFull(dirFn, p) {
    return simWithRisk(allBars, C, ET, dirFn, p);
  }

  console.log("Running " + METHODS.length + " methods x " + CONFIGS.length + " configs...\n");

  var results = [];
  for (var mi = 0; mi < METHODS.length; mi++) {
    var name = METHODS[mi][0];
    var fn   = METHODS[mi][1];
    process.stdout.write("  " + (mi + 1) + "/" + METHODS.length + " " + name + "... ");

    var best13net = -Infinity, bestR = null, bestCfg = null;
    for (var ci = 0; ci < CONFIGS.length; ci++) {
      var p    = CONFIGS[ci];
      var r13  = run13(fn, p);
      var rFull = runFull(fn, p);
      if (r13.net$ > best13net) {
        best13net = r13.net$;
        var cp = combinePass(rFull.trades);
        var mc = mcPass(rFull.trades);
        bestR  = { r13: r13, rFull: rFull, cp: cp, mc: mc };
        bestCfg = p;
      }
    }
    console.log("13d " + dol(bestR.r13.net$) + "  full " + dol(bestR.rFull.net$));
    results.push({ name: name, cfg: bestCfg, r13: bestR.r13, rFull: bestR.rFull, cp: bestR.cp, mc: bestR.mc });
  }

  results.sort(function(a, b) { return b.r13.net$ - a.r13.net$; });

  // ---- console table ----
  console.log("\n" + "=".repeat(120));
  console.log("  STRATEGY BATTLE - 13-DAY WINDOW  (net of fee + 2-tick slippage)");
  console.log("=".repeat(120));
  var hdr = "Strategy".padEnd(36) + " Config".padEnd(23) +
    "13d-Net".padStart(10) + "13d-Trd/Win".padStart(13) + "13d-PF".padStart(8) +
    " | " + "Full-Net".padStart(10) + "Full-Win".padStart(10) + "Full-DD".padStart(10) +
    "Feasible".padStart(10) + "Combine".padStart(10) + "MC%".padStart(7);
  console.log(hdr);
  console.log("-".repeat(120));
  for (var ri = 0; ri < results.length; ri++) {
    var r = results[ri];
    var cfgS = "s" + r.cfg.stopMult + "/t" + r.cfg.tgtMult + " $" + r.cfg.riskCap + " " + r.cfg.maxTr + "/d";
    var feasI = r.rFull.feasible ? "YES" : "NO ";
    var passI = r.cp.passed ? "PASS" : "FAIL-" + r.cp.why;
    console.log(
      r.name.slice(0, 35).padEnd(36) + cfgS.padEnd(23) +
      dol(r.r13.net$).padStart(10) +
      (r.r13.n + "t " + pct(r.r13.win)).padStart(13) +
      String(r.r13.pf).padStart(8) +
      " | " +
      dol(r.rFull.net$).padStart(10) +
      (r.rFull.n + "t " + pct(r.rFull.win)).padStart(10) +
      ("-$" + r.rFull.maxDD$).padStart(10) +
      feasI.padStart(10) +
      passI.padStart(10) +
      (r.mc + "%").padStart(7)
    );
  }

  // ---- top 3 day-by-day ----
  console.log("\n" + "=".repeat(120));
  console.log("  TOP 3 DAY-BY-DAY BREAKDOWN (13d window)");
  console.log("=".repeat(120));
  for (var ti = 0; ti < Math.min(3, results.length); ti++) {
    var r = results[ti];
    console.log("\n[" + (ti+1) + "] " + r.name);
    console.log("    Config: s" + r.cfg.stopMult + "/t" + r.cfg.tgtMult + " $" + r.cfg.riskCap + " risk-cap, " + r.cfg.maxTr + "/day, " + r.cfg.dayStop + " daily-stop");
    console.log("    13d:  " + dol(r.r13.net$) + " | " + r.r13.n + " trades | " + pct(r.r13.win) + " win | PF " + r.r13.pf + " | MaxDD -$" + r.r13.maxDD$ + " | WorstDay -$" + r.r13.worstDay$);
    console.log("    Full: " + dol(r.rFull.net$) + " | " + r.rFull.n + " trades | " + pct(r.rFull.win) + " win | MaxDD -$" + r.rFull.maxDD$ + " | Feasible: " + (r.rFull.feasible ? "YES" : "NO"));
    console.log("    Combine: " + (r.cp.passed ? "PASS" : "FAIL (" + r.cp.why + ")") + " | MC: " + r.mc + "%");
    if (r.r13.byDay && r.r13.byDay.size) {
      var sorted = Array.from(r.r13.byDay.entries()).sort(function(a, b) { return a[0].localeCompare(b[0]); });
      for (var di = 0; di < sorted.length; di++) {
        console.log("    " + sorted[di][0] + ": " + dol(sorted[di][1]));
      }
    }
  }

  // ---- markdown report ----
  var lines = [];
  lines.push("# Strategy Battle - 13-Day Window (" + new Date().toISOString().slice(0, 10) + ")");
  lines.push("");
  lines.push("**Data:** NQ 5m, " + allBars.length + " bars, " + first + " to " + last);
  lines.push("**13d window:** " + last13[0] + " to " + last13[last13.length-1]);
  lines.push("**Cost model:** fee $" + FEE + "/side + " + SLIP + "-tick slippage, vol-sized ($200 risk cap, max 5 MNQ)");
  lines.push("**Risk gates:** max " + CONFIGS[0].maxTr + " trades/day, daily stop -$700, feasibility hard gate (DD<$2k, worst-day<$1k)");
  lines.push("");
  lines.push("## Results - ranked by 13d net P&L");
  lines.push("");
  lines.push("| # | Strategy | Config | 13d Net | 13d Trd | 13d Win | 13d PF | Full Net | Feasible | Combine | MC% |");
  lines.push("|---|---|---|---:|---:|---:|---:|---:|:---:|:---:|---:|");
  for (var ri = 0; ri < results.length; ri++) {
    var r = results[ri];
    var cfgS = "s" + r.cfg.stopMult + "/t" + r.cfg.tgtMult + " $" + r.cfg.riskCap + " " + r.cfg.maxTr + "/d";
    lines.push("| " + (ri+1) + " | " + r.name + " | " + cfgS + " | " + dol(r.r13.net$) + " | " + r.r13.n + " | " + pct(r.r13.win) + " | " + r.r13.pf + " | " + dol(r.rFull.net$) + " | " + (r.rFull.feasible ? "YES" : "NO") + " | " + (r.cp.passed ? "PASS" : "FAIL-" + r.cp.why) + " | " + r.mc + "% |");
  }

  lines.push("");
  lines.push("## Top 3 - Day-by-Day (13d window)");
  lines.push("");
  for (var ti = 0; ti < Math.min(3, results.length); ti++) {
    var r = results[ti];
    lines.push("### " + (ti+1) + ". " + r.name);
    lines.push("Config: s" + r.cfg.stopMult + "/t" + r.cfg.tgtMult + " $" + r.cfg.riskCap + ", " + r.cfg.maxTr + "/day, " + r.cfg.dayStop + " daily stop");
    lines.push("- **13d:** " + dol(r.r13.net$) + " | " + r.r13.n + " trades | " + pct(r.r13.win) + " win | PF " + r.r13.pf + " | MaxDD -$" + r.r13.maxDD$ + " | WorstDay -$" + r.r13.worstDay$);
    lines.push("- **Full period:** " + dol(r.rFull.net$) + " | " + r.rFull.n + " trades | " + pct(r.rFull.win) + " win | MaxDD -$" + r.rFull.maxDD$ + " | Feasible: " + (r.rFull.feasible ? "YES" : "NO"));
    lines.push("- **Combine:** " + (r.cp.passed ? "PASS" : "FAIL (" + r.cp.why + ")") + "  |  Monte-Carlo: " + r.mc + "%");
    if (r.r13.byDay && r.r13.byDay.size) {
      lines.push("");
      lines.push("| Date | P&L |");
      lines.push("|---|---|");
      var sorted = Array.from(r.r13.byDay.entries()).sort(function(a, b) { return a[0].localeCompare(b[0]); });
      for (var di = 0; di < sorted.length; di++) {
        lines.push("| " + sorted[di][0] + " | " + dol(sorted[di][1]) + " |");
      }
    }
    lines.push("");
  }

  var outPath = path.join(__dirname, "logs", "strat-battle-13d-report.md");
  fs.writeFileSync(outPath, lines.join("\n") + "\n");
  console.log("\nReport saved: logs/strat-battle-13d-report.md");
})();
