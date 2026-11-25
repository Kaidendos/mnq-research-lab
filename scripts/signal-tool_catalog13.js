// =============================================================
//  catalog13.js — distinct-METHOD screen on the 13-day chart.
//
//  Goal: test the EDGE of many genuinely different entry methods, not
//  parameter tweaks. Every candidate is forced through ONE common exit
//  (stop 1.2xATR / target 1.8xATR, RTH entries, flat by 16:00 ET, one
//  position at a time, stop-first on ties) reused verbatim from lab-new4.
//  So the only thing that varies between candidates is the ENTRY METHOD —
//  no per-method stop/target/gate tuning ("optimizations").
//
//  Field = 50 existing methods (lab-new4 buildAll, dir-extracted) + ~72 new
//  distinct methods authored here + the locked champion as benchmark = ~123.
//
//  Samples:
//    13d = CSV_13 (cached MNQ 5m TradingView export) — PRIMARY (the "13-day chart").
//    58d = data/nq-5m.json (cached NQ=F 5m) — robustness confirmation column.
//
//  DATA-ONLY / TopStep-compliant: reads local data, never places an order.
//  The live bot + strategies/champion.json are untouched.
//
//  Run:  node catalog13.js
// =============================================================
"use strict";

const fs = require("fs");
const path = require("path");
require("./public/indicators.js");
const I = globalThis.Indicators;
const Lab = require("./lab-new4");

const PV = 2, CONTRACTS = 5, DPP = PV * CONTRACTS; // $/pt @ 5 MNQ = 10
const DLL = 1000, MLL = 2000;
const STOP_MULT = 1.2, TGT_MULT = 1.8;             // COMMON exit for ALL methods
const OUT_JSON = path.join(__dirname, "logs", "catalog13-results.json");
const OUT_MD = path.join(__dirname, "logs", "catalog13-report.md");

const RTH_START = 570, RTH_END = 960;
const ep = Lab.etParts, dkOf = Lab.dayKeyOf;

// ---------------- self-contained indicator helpers ----------------
function rollPriorMax(arr, n) { const o = new Array(arr.length).fill(null); for (let i = n; i < arr.length; i++) { let m = -Infinity; for (let k = i - n; k < i; k++) m = Math.max(m, arr[k]); o[i] = m; } return o; }
function rollPriorMin(arr, n) { const o = new Array(arr.length).fill(null); for (let i = n; i < arr.length; i++) { let m = Infinity; for (let k = i - n; k < i; k++) m = Math.min(m, arr[k]); o[i] = m; } return o; }
function stoch(h, l, c, n) { const K = new Array(c.length).fill(null); for (let i = n - 1; i < c.length; i++) { let hh = -Infinity, ll = Infinity; for (let k = i - n + 1; k <= i; k++) { hh = Math.max(hh, h[k]); ll = Math.min(ll, l[k]); } K[i] = hh > ll ? (c[i] - ll) / (hh - ll) * 100 : 50; } const D = I.sma(K.map((v) => v == null ? 0 : v), 3).map((v, i) => K[i] == null ? null : v); return { K, D }; }
function cciCalc(h, l, c, n) { const tp = h.map((x, i) => (x + l[i] + c[i]) / 3), ma = I.sma(tp, n), o = new Array(c.length).fill(null); for (let i = n - 1; i < c.length; i++) { let md = 0; for (let k = i - n + 1; k <= i; k++) md += Math.abs(tp[k] - ma[i]); md /= n; o[i] = md === 0 ? 0 : (tp[i] - ma[i]) / (0.015 * md); } return o; }
function wprCalc(h, l, c, n) { const o = new Array(c.length).fill(null); for (let i = n - 1; i < c.length; i++) { let hh = -Infinity, ll = Infinity; for (let k = i - n + 1; k <= i; k++) { hh = Math.max(hh, h[k]); ll = Math.min(ll, l[k]); } o[i] = hh > ll ? -100 * (hh - c[i]) / (hh - ll) : -50; } return o; }
function vwapBands(bars) { const vwap = new Array(bars.length).fill(null), sd = new Array(bars.length).fill(null); let cur = null, vN = 0, vD = 0, vN2 = 0; for (let i = 0; i < bars.length; i++) { const p = ep(bars[i].t); if (p.k !== cur) { cur = p.k; vN = 0; vD = 0; vN2 = 0; } if (p.mins >= RTH_START && p.mins < RTH_END) { const hlc3 = (bars[i].h + bars[i].l + bars[i].c) / 3, v = bars[i].v || 1; vN += hlc3 * v; vN2 += hlc3 * hlc3 * v; vD += v; } if (vD > 0) { const m = vN / vD; vwap[i] = m; sd[i] = Math.sqrt(Math.max(0, vN2 / vD - m * m)); } } return { vwap, sd }; }
function rocCalc(c, n) { return c.map((x, i) => (i < n || c[i - n] === 0) ? null : (x - c[i - n]) / c[i - n] * 100); }
function heikin(bars) { const haC = new Array(bars.length), haO = new Array(bars.length); for (let i = 0; i < bars.length; i++) { haC[i] = (bars[i].o + bars[i].h + bars[i].l + bars[i].c) / 4; haO[i] = i === 0 ? (bars[i].o + bars[i].c) / 2 : (haO[i - 1] + haC[i - 1]) / 2; } return { haO, haC }; }
function lastSwing(arr, isHigh, left, right) { const n = arr.length, o = new Array(n).fill(null); let last = null; for (let i = 0; i < n; i++) { const c = i - right; if (c >= left) { let piv = true; for (let k = 1; k <= left && piv; k++) if (isHigh ? arr[c - k] > arr[c] : arr[c - k] < arr[c]) piv = false; for (let k = 1; k <= right && piv; k++) if (isHigh ? arr[c + k] > arr[c] : arr[c + k] < arr[c]) piv = false; if (piv) last = arr[c]; } o[i] = last; } return o; }
function supertrend(bars, mult, n) { const h = bars.map(b => b.h), l = bars.map(b => b.l), c = bars.map(b => b.c); const atr = I.atr(h, l, c, n); const dir = new Array(bars.length).fill(0); let fU = null, fL = null, trend = 1; for (let i = 0; i < bars.length; i++) { if (atr[i] == null || i === 0) continue; const mid = (h[i] + l[i]) / 2, bU = mid + mult * atr[i], bL = mid - mult * atr[i]; fU = (fU == null || bU < fU || c[i - 1] > fU) ? bU : fU; fL = (fL == null || bL > fL || c[i - 1] < fL) ? bL : fL; if (c[i] > fU) trend = 1; else if (c[i] < fL) trend = -1; dir[i] = trend; } return dir; }

// per-bar intraday running HOD/LOD, day open, prior-day HLC, OBV
function sessionArrays(bars) {
  const N = bars.length;
  const hod = new Array(N).fill(null), lod = new Array(N).fill(null), dOpen = new Array(N).fill(null);
  const pdH = new Array(N).fill(null), pdL = new Array(N).fill(null), pdC = new Array(N).fill(null);
  const obv = new Array(N).fill(null);
  const order = [], H = new Map(), L = new Map(), C = new Map();
  let curDay = null, curHi = -Infinity, curLo = Infinity, curOpen = null, curObv = 0;
  for (let i = 0; i < N; i++) {
    const p = ep(bars[i].t), k = p.k, inR = p.mins >= RTH_START && p.mins < RTH_END && p.day !== 0 && p.day !== 6;
    if (k !== curDay) { curDay = k; curHi = -Infinity; curLo = Infinity; curOpen = null; curObv = 0; }
    if (inR) {
      if (curOpen == null) { curOpen = bars[i].o; order.push(k); }
      curHi = Math.max(curHi, bars[i].h); curLo = Math.min(curLo, bars[i].l);
      H.set(k, curHi); L.set(k, curLo); C.set(k, bars[i].c);
      curObv += (i > 0 ? Math.sign(bars[i].c - bars[i - 1].c) : 0) * (bars[i].v || 1);
    }
    hod[i] = curHi === -Infinity ? null : curHi; lod[i] = curLo === Infinity ? null : curLo;
    dOpen[i] = curOpen; obv[i] = curObv;
    const idx = order.indexOf(k);
    if (idx > 0) { const pk = order[idx - 1]; pdH[i] = H.get(pk); pdL[i] = L.get(pk); pdC[i] = C.get(pk); }
  }
  return { hod, lod, dOpen, pdH, pdL, pdC, obv };
}
function efficiencyRatio(c, n) { const o = new Array(c.length).fill(null); for (let i = n; i < c.length; i++) { let vol = 0; for (let k = i - n + 1; k <= i; k++) vol += Math.abs(c[k] - c[k - 1]); o[i] = vol === 0 ? 0 : Math.abs(c[i] - c[i - n]) / vol; } return o; }

// ---------------- build full indicator context ----------------
function ctxOf(bars) {
  const o = bars.map(b => b.o), h = bars.map(b => b.h), l = bars.map(b => b.l), c = bars.map(b => b.c), v = bars.map(b => b.v);
  const dmi = I.dmi(h, l, c, 14, 14);
  const pDI = dmi.plusDI || dmi.diPlus || dmi.plus || dmi.pdi, mDI = dmi.minusDI || dmi.diMinus || dmi.minus || dmi.mdi, adx = dmi.adx || dmi.adxV || dmi.ADX;
  const { macdLine, signalLine } = I.macd(c, 12, 26, 9);
  const hist = macdLine.map((x, k) => (x == null || signalLine[k] == null) ? null : x - signalLine[k]);
  const dev = I.stdev(c, 20), sma20 = I.sma(c, 20);
  const bbU = sma20.map((x, k) => x == null ? null : x + 2 * dev[k]), bbL = sma20.map((x, k) => x == null ? null : x - 2 * dev[k]);
  const pctB = c.map((x, k) => (bbU[k] == null || bbU[k] === bbL[k]) ? null : (x - bbL[k]) / (bbU[k] - bbL[k]));
  const ema20 = I.ema(c, 20), atr20 = I.atr(h, l, c, 20);
  const { K, D } = stoch(h, l, c, 14);
  const { vwap, sd } = vwapBands(bars);
  const { haO, haC } = heikin(bars);
  const sess = sessionArrays(bars);
  const ibs = c.map((x, k) => (h[k] === l[k]) ? 0.5 : (x - l[k]) / (h[k] - l[k]));
  return {
    o, h, l, c, v, bars, N: bars.length,
    atr: I.atr(h, l, c, 14), atr5: I.atr(h, l, c, 5), atr20,
    ema8: I.ema(c, 8), ema9: I.ema(c, 9), ema20, ema21: I.ema(c, 21), ema50: I.ema(c, 50), ema200: I.ema(c, 200),
    sma10: I.sma(c, 10), sma20, sma50: I.sma(c, 50),
    dev, bbU, bbL, pctB,
    rsi2: I.rsi(c, 2), rsi7: I.rsi(c, 7), rsi14: I.rsi(c, 14),
    macd: macdLine, sig: signalLine, hist,
    pDI, mDI, adx,
    K, D, cci: cciCalc(h, l, c, 20), wpr: wprCalc(h, l, c, 14),
    vwap, sd, roc: rocCalc(c, 10), haO, haC,
    don20H: rollPriorMax(h, 20), don20L: rollPriorMin(l, 20), don50H: rollPriorMax(h, 50),
    keltU: ema20.map((x, k) => x == null || atr20[k] == null ? null : x + 1.5 * atr20[k]),
    keltL: ema20.map((x, k) => x == null || atr20[k] == null ? null : x - 1.5 * atr20[k]),
    ibs, hod: sess.hod, lod: sess.lod, dOpen: sess.dOpen, pdH: sess.pdH, pdL: sess.pdL, pdC: sess.pdC, obv: sess.obv,
    er: efficiencyRatio(c, 10), st: supertrend(bars, 3, 10),
    swingH: lastSwing(h, true, 3, 3), swingL: lastSwing(l, false, 3, 3),
    mins: bars.map(b => ep(b.t).mins),
  };
}

const xUp = (a, b, i) => a[i - 1] != null && a[i] != null && b[i - 1] != null && b[i] != null && a[i - 1] <= b[i - 1] && a[i] > b[i];
const xDn = (a, b, i) => a[i - 1] != null && a[i] != null && b[i - 1] != null && b[i] != null && a[i - 1] >= b[i - 1] && a[i] < b[i];

// ---------------- ~72 NEW distinct entry methods: fn(C,i) -> -1|0|1 ----------------
const NEW = [
  // ----- mean-reversion / fade -----
  ["n01_stochOSX", "Stochastic %K cross 20/80", "MR", (C, i) => { if (C.K[i] == null || C.K[i - 1] == null) return 0; if (C.K[i - 1] < 20 && C.K[i] >= 20) return 1; if (C.K[i - 1] > 80 && C.K[i] <= 80) return -1; return 0; }],
  ["n02_rsi7Ext", "RSI(7) extreme fade", "MR", (C, i) => { if (C.rsi7[i] == null) return 0; if (C.rsi7[i] < 10) return 1; if (C.rsi7[i] > 90) return -1; return 0; }],
  ["n03_pctBReclaim", "Bollinger %B reclaim 0/1", "MR", (C, i) => { if (C.pctB[i] == null || C.pctB[i - 1] == null) return 0; if (C.pctB[i - 1] < 0 && C.pctB[i] >= 0) return 1; if (C.pctB[i - 1] > 1 && C.pctB[i] <= 1) return -1; return 0; }],
  ["n04_ibsExt", "Internal Bar Strength extreme", "MR", (C, i) => { if (C.sma20[i] == null) return 0; if (C.ibs[i] < 0.1 && C.c[i] < C.sma20[i]) return 1; if (C.ibs[i] > 0.9 && C.c[i] > C.sma20[i]) return -1; return 0; }],
  ["n05_fiveLL", "Five lower-lows bounce", "MR", (C, i) => { let ll = true, hh = true; for (let k = 0; k < 5; k++) { if (C.l[i - k] >= C.l[i - k - 1]) ll = false; if (C.h[i - k] <= C.h[i - k - 1]) hh = false; } if (ll && C.c[i] > C.o[i]) return 1; if (hh && C.c[i] < C.o[i]) return -1; return 0; }],
  ["n06_climaxFade", "Climax bar (>3xATR) fade", "MR", (C, i) => { const a = C.atr[i]; if (a == null) return 0; const rng = C.h[i] - C.l[i]; if (rng < 3 * a) return 0; if (C.c[i] <= C.l[i] + 0.33 * rng) return 1; if (C.c[i] >= C.h[i] - 0.33 * rng) return -1; return 0; }],
  ["n07_vwapMildFade", "VWAP 1.5-sigma fade", "MR", (C, i) => { if (C.vwap[i] == null || !(C.sd[i] > 0)) return 0; const z = (C.c[i] - C.vwap[i]) / C.sd[i]; if (z <= -1.5 && C.c[i] > C.o[i]) return 1; if (z >= 1.5 && C.c[i] < C.o[i]) return -1; return 0; }],
  ["n08_pdLowTag", "Prior-day low tag bounce", "MR", (C, i) => { if (C.pdL[i] == null || C.pdH[i] == null) return 0; if (C.l[i] <= C.pdL[i] && C.c[i] > C.pdL[i]) return 1; if (C.h[i] >= C.pdH[i] && C.c[i] < C.pdH[i]) return -1; return 0; }],
  ["n09_connorsRsi2", "Connors RSI(2)+EMA200 filter", "MR", (C, i) => { if (C.rsi2[i] == null || C.ema200[i] == null) return 0; if (C.rsi2[i] < 10 && C.c[i] > C.ema200[i]) return 1; if (C.rsi2[i] > 90 && C.c[i] < C.ema200[i]) return -1; return 0; }],
  ["n10_gapDnReclaim", "Gap-down reclaim prior low", "MR", (C, i) => { if (C.pdL[i] == null || C.dOpen[i] == null) return 0; if (C.dOpen[i] < C.pdL[i] && C.c[i] > C.pdL[i] && C.c[i] > C.o[i]) return 1; if (C.pdH[i] != null && C.dOpen[i] > C.pdH[i] && C.c[i] < C.pdH[i] && C.c[i] < C.o[i]) return -1; return 0; }],
  ["n11_dojiBBrev", "Doji at BB extreme reversal", "MR", (C, i) => { const a = C.atr[i]; if (a == null || C.bbL[i] == null) return 0; const body = Math.abs(C.c[i] - C.o[i]); if (body > 0.2 * a) return 0; if (C.l[i] <= C.bbL[i]) return 1; if (C.h[i] >= C.bbU[i]) return -1; return 0; }],
  ["n12_keyRev", "Key reversal bar", "MR", (C, i) => { let nl = true, nh = true; for (let k = 1; k <= 5; k++) { if (C.l[i] >= C.l[i - k]) nl = false; if (C.h[i] <= C.h[i - k]) nh = false; } if (nl && C.c[i] > C.o[i] && C.c[i] > C.c[i - 1]) return 1; if (nh && C.c[i] < C.o[i] && C.c[i] < C.c[i - 1]) return -1; return 0; }],
  ["n13_cci0trend", "CCI zero-cross with trend", "MR", (C, i) => { if (C.cci[i] == null || C.cci[i - 1] == null || C.ema200[i] == null) return 0; if (C.cci[i - 1] < 0 && C.cci[i] >= 0 && C.c[i] > C.ema200[i]) return 1; if (C.cci[i - 1] > 0 && C.cci[i] <= 0 && C.c[i] < C.ema200[i]) return -1; return 0; }],
  ["n14_wprMid", "Williams %R mid (-50) cross", "MR", (C, i) => { if (C.wpr[i] == null || C.wpr[i - 1] == null) return 0; if (C.wpr[i - 1] <= -50 && C.wpr[i] > -50) return 1; if (C.wpr[i - 1] >= -50 && C.wpr[i] < -50) return -1; return 0; }],
  ["n15_rsiFailSwing", "RSI(14) failure swing", "MR", (C, i) => { if (C.rsi14[i] == null || C.rsi14[i - 1] == null) return 0; if (C.rsi14[i - 1] < 30 && C.rsi14[i] >= 30) return 1; if (C.rsi14[i - 1] > 70 && C.rsi14[i] <= 70) return -1; return 0; }],
  // ----- momentum / trend -----
  ["n16_ema9_21x", "EMA9 / EMA21 cross", "MOM", (C, i) => { if (xUp(C.ema9, C.ema21, i)) return 1; if (xDn(C.ema9, C.ema21, i)) return -1; return 0; }],
  ["n17_ema20_50x", "EMA20 / EMA50 cross", "MOM", (C, i) => { if (xUp(C.ema20, C.ema50, i)) return 1; if (xDn(C.ema20, C.ema50, i)) return -1; return 0; }],
  ["n18_tripleEma", "Triple-EMA alignment pullback", "MOM", (C, i) => { if (C.ema8[i] == null || C.ema50[i] == null) return 0; const bull = C.ema8[i] > C.ema21[i] && C.ema21[i] > C.ema50[i], bear = C.ema8[i] < C.ema21[i] && C.ema21[i] < C.ema50[i]; if (bull && C.l[i] <= C.ema21[i] && C.c[i] > C.ema8[i]) return 1; if (bear && C.h[i] >= C.ema21[i] && C.c[i] < C.ema8[i]) return -1; return 0; }],
  ["n19_supertrend", "SuperTrend(3,10) flip", "MOM", (C, i) => { if (C.st[i - 1] === 0) return 0; if (C.st[i] === 1 && C.st[i - 1] === -1) return 1; if (C.st[i] === -1 && C.st[i - 1] === 1) return -1; return 0; }],
  ["n20_rocZero", "ROC(10) zero-cross with trend", "MOM", (C, i) => { if (C.roc[i] == null || C.roc[i - 1] == null || C.ema200[i] == null) return 0; if (C.roc[i - 1] <= 0 && C.roc[i] > 0 && C.c[i] > C.ema200[i]) return 1; if (C.roc[i - 1] >= 0 && C.roc[i] < 0 && C.c[i] < C.ema200[i]) return -1; return 0; }],
  ["n21_vwapReclaim", "Session VWAP reclaim", "MOM", (C, i) => { if (xUp(C.c, C.vwap, i)) return 1; if (xDn(C.c, C.vwap, i)) return -1; return 0; }],
  ["n22_ema200x", "EMA200 reclaim cross", "MOM", (C, i) => { if (xUp(C.c, C.ema200, i)) return 1; if (xDn(C.c, C.ema200, i)) return -1; return 0; }],
  ["n23_histRising3", "MACD histogram rising x3", "MOM", (C, i) => { if (C.hist[i] == null || C.hist[i - 2] == null) return 0; if (C.hist[i] > 0 && C.hist[i] > C.hist[i - 1] && C.hist[i - 1] > C.hist[i - 2]) return 1; if (C.hist[i] < 0 && C.hist[i] < C.hist[i - 1] && C.hist[i - 1] < C.hist[i - 2]) return -1; return 0; }],
  ["n24_hhhl", "Higher-high + higher-low structure", "MOM", (C, i) => { if (C.h[i] > C.h[i - 1] && C.l[i] > C.l[i - 1] && C.h[i - 1] > C.h[i - 2] && C.l[i - 1] > C.l[i - 2]) return 1; if (C.l[i] < C.l[i - 1] && C.h[i] < C.h[i - 1] && C.l[i - 1] < C.l[i - 2] && C.h[i - 1] < C.h[i - 2]) return -1; return 0; }],
  ["n25_breakHOD", "Break of intraday HOD/LOD", "MOM", (C, i) => { if (C.hod[i - 1] == null) return 0; if (C.c[i] > C.hod[i - 1] && C.c[i] > C.o[i]) return 1; if (C.c[i] < C.lod[i - 1] && C.c[i] < C.o[i]) return -1; return 0; }],
  ["n26_stochKDtrend", "Stoch K/D cross <50 with trend", "MOM", (C, i) => { if (C.K[i] == null || C.ema200[i] == null) return 0; if (xUp(C.K, C.D, i) && C.K[i] < 50 && C.c[i] > C.ema200[i]) return 1; if (xDn(C.K, C.D, i) && C.K[i] > 50 && C.c[i] < C.ema200[i]) return -1; return 0; }],
  ["n27_adx25brk", "ADX cross 25 + DI direction", "MOM", (C, i) => { if (!C.adx || C.adx[i] == null || C.adx[i - 1] == null) return 0; if (C.adx[i - 1] <= 25 && C.adx[i] > 25) { if (C.pDI[i] > C.mDI[i]) return 1; if (C.mDI[i] > C.pDI[i]) return -1; } return 0; }],
  ["n28_ribbonExp", "EMA8-21 spread expansion", "MOM", (C, i) => { if (C.ema8[i] == null) return 0; const a = C.atr[i]; if (a == null) return 0; const s = C.ema8[i] - C.ema21[i], sp = C.ema8[i - 1] - C.ema21[i - 1]; if (s > 0.2 * a && s > sp && C.c[i] > C.o[i]) return 1; if (s < -0.2 * a && s < sp && C.c[i] < C.o[i]) return -1; return 0; }],
  ["n29_mom5bar", "5-bar momentum vs ATR + EMA50", "MOM", (C, i) => { const a = C.atr[i]; if (a == null || C.ema50[i] == null) return 0; if (C.c[i] - C.c[i - 5] > a && C.c[i] > C.ema50[i]) return 1; if (C.c[i - 5] - C.c[i] > a && C.c[i] < C.ema50[i]) return -1; return 0; }],
  ["n30_newHigh50", "New 50-bar high run", "MOM", (C, i) => { if (C.don50H[i] == null) return 0; if (C.c[i] > C.don50H[i]) return 1; return 0; }],
  // ----- breakout / volatility -----
  ["n31_orb30", "Opening-range (30m) break", "BRK", (C, i) => { if (C.mins[i] < 600 || C.mins[i] > 780) return 0; if (C.hod[i - 1] == null) return 0; if (C.c[i] > C.hod[i - 1]) return 1; if (C.c[i] < C.lod[i - 1]) return -1; return 0; }],
  ["n32_firstBarBrk", "First 5m-bar high/low break", "BRK", (C, i) => { if (C.mins[i] < 575 || C.mins[i] > 660) return 0; if (C.hod[i - 1] == null) return 0; if (C.c[i] > C.hod[i - 1] && C.c[i] > C.o[i]) return 1; if (C.c[i] < C.lod[i - 1] && C.c[i] < C.o[i]) return -1; return 0; }],
  ["n33_insideBarBrk", "Inside-bar break", "BRK", (C, i) => { if (C.h[i - 1] >= C.h[i - 2] || C.l[i - 1] <= C.l[i - 2]) return 0; if (C.c[i] > C.h[i - 1]) return 1; if (C.c[i] < C.l[i - 1]) return -1; return 0; }],
  ["n34_squeezeRank", "BB-width squeeze-rank break", "BRK", (C, i) => { if (C.bbU[i] == null) return 0; const w = C.bbU[i] - C.bbL[i]; let mn = Infinity; for (let k = 0; k < 50; k++) { if (C.bbU[i - k] == null) return 0; mn = Math.min(mn, C.bbU[i - k] - C.bbL[i - k]); } if (w > 1.05 * mn) return 0; if (C.c[i] > C.o[i] && C.c[i] > C.sma20[i]) return 1; if (C.c[i] < C.o[i] && C.c[i] < C.sma20[i]) return -1; return 0; }],
  ["n35_atrContractBrk", "ATR-contraction then break", "BRK", (C, i) => { const a = C.atr[i]; if (a == null || C.atr[i - 5] == null) return 0; if (a > 0.85 * C.atr[i - 5]) return 0; if (C.c[i] > C.h[i - 1]) return 1; if (C.c[i] < C.l[i - 1]) return -1; return 0; }],
  ["n36_liqSweep", "Liquidity sweep reclaim", "BRK", (C, i) => { if (C.swingL[i] == null || C.swingH[i] == null) return 0; if (C.l[i] < C.swingL[i] && C.c[i] > C.swingL[i] && C.c[i] > C.o[i]) return 1; if (C.h[i] > C.swingH[i] && C.c[i] < C.swingH[i] && C.c[i] < C.o[i]) return -1; return 0; }],
  ["n37_swingBrk", "Swing high/low break", "BRK", (C, i) => { if (C.swingH[i] == null || C.swingL[i] == null || C.swingH[i - 1] == null || C.swingL[i - 1] == null) return 0; if (C.c[i] > C.swingH[i] && C.c[i - 1] <= C.swingH[i - 1]) return 1; if (C.c[i] < C.swingL[i] && C.c[i - 1] >= C.swingL[i - 1]) return -1; return 0; }],
  ["n38_wideRangeFollow", "Wide-range-bar follow-through", "BRK", (C, i) => { const a = C.atr[i]; if (a == null) return 0; if (C.h[i - 1] - C.l[i - 1] < 2 * a) return 0; if (C.c[i - 1] > C.o[i - 1] && C.c[i] > C.h[i - 1]) return 1; if (C.c[i - 1] < C.o[i - 1] && C.c[i] < C.l[i - 1]) return -1; return 0; }],
  ["n39_orbRetest", "Opening-range break + retest", "BRK", (C, i) => { if (C.mins[i] < 600 || C.mins[i] > 810 || C.hod[i - 1] == null) return 0; const a = C.atr[i]; if (a == null) return 0; if (C.l[i] <= C.hod[i - 1] + 0.3 * a && C.c[i] > C.hod[i - 1] && C.c[i] > C.o[i]) return 1; if (C.h[i] >= C.lod[i - 1] - 0.3 * a && C.c[i] < C.lod[i - 1] && C.c[i] < C.o[i]) return -1; return 0; }],
  ["n40_keltBrk", "Keltner upper/lower break", "BRK", (C, i) => { if (C.keltU[i] == null || C.keltU[i - 1] == null) return 0; if (C.c[i] > C.keltU[i] && C.c[i - 1] <= C.keltU[i - 1]) return 1; if (C.c[i] < C.keltL[i] && C.c[i - 1] >= C.keltL[i - 1]) return -1; return 0; }],
  // ----- candle patterns -----
  ["n41_harami", "Harami (inside body) reversal", "PAT", (C, i) => { const b1 = Math.abs(C.c[i - 1] - C.o[i - 1]), b0 = Math.abs(C.c[i] - C.o[i]); if (b0 >= b1 || b1 === 0) return 0; const hi = Math.max(C.c[i], C.o[i]), lo = Math.min(C.c[i], C.o[i]); if (hi < Math.max(C.c[i - 1], C.o[i - 1]) && lo > Math.min(C.c[i - 1], C.o[i - 1])) { if (C.c[i - 1] < C.o[i - 1]) return 1; if (C.c[i - 1] > C.o[i - 1]) return -1; } return 0; }],
  ["n42_tweezer", "Tweezer bottom/top", "PAT", (C, i) => { const a = C.atr[i]; if (a == null) return 0; if (Math.abs(C.l[i] - C.l[i - 1]) < 0.1 * a && C.c[i - 1] < C.o[i - 1] && C.c[i] > C.o[i]) return 1; if (Math.abs(C.h[i] - C.h[i - 1]) < 0.1 * a && C.c[i - 1] > C.o[i - 1] && C.c[i] < C.o[i]) return -1; return 0; }],
  ["n43_outsideRev", "Outside-bar reversal", "PAT", (C, i) => { if (C.h[i] > C.h[i - 1] && C.l[i] < C.l[i - 1]) { if (C.c[i] > C.o[i] && C.c[i - 1] < C.o[i - 1]) return 1; if (C.c[i] < C.o[i] && C.c[i - 1] > C.o[i - 1]) return -1; } return 0; }],
  ["n44_threeInside", "Three-inside up/down", "PAT", (C, i) => { const downBig = C.c[i - 2] < C.o[i - 2], upBig = C.c[i - 2] > C.o[i - 2]; const insideUp = C.c[i - 1] > C.o[i - 1] && Math.max(C.c[i - 1], C.o[i - 1]) < Math.max(C.c[i - 2], C.o[i - 2]); const insideDn = C.c[i - 1] < C.o[i - 1] && Math.min(C.c[i - 1], C.o[i - 1]) > Math.min(C.c[i - 2], C.o[i - 2]); if (downBig && insideUp && C.c[i] > C.h[i - 1]) return 1; if (upBig && insideDn && C.c[i] < C.l[i - 1]) return -1; return 0; }],
  ["n45_marubozu", "Marubozu continuation", "PAT", (C, i) => { const rng = C.h[i] - C.l[i], body = Math.abs(C.c[i] - C.o[i]); if (rng === 0 || body < 0.9 * rng || C.ema50[i] == null) return 0; if (C.c[i] > C.o[i] && C.c[i] > C.ema50[i]) return 1; if (C.c[i] < C.o[i] && C.c[i] < C.ema50[i]) return -1; return 0; }],
  ["n46_dojiBrk", "Doji-range break", "PAT", (C, i) => { const a = C.atr[i]; if (a == null) return 0; const body1 = Math.abs(C.c[i - 1] - C.o[i - 1]); if (body1 > 0.15 * a) return 0; if (C.c[i] > C.h[i - 1]) return 1; if (C.c[i] < C.l[i - 1]) return -1; return 0; }],
  ["n47_hammerLOD", "Hammer at LOD / star at HOD", "PAT", (C, i) => { const body = Math.abs(C.c[i] - C.o[i]), loW = Math.min(C.c[i], C.o[i]) - C.l[i], upW = C.h[i] - Math.max(C.c[i], C.o[i]); if (C.lod[i] != null && loW > 2 * body && C.l[i] <= C.lod[i] + 0.01) return 1; if (C.hod[i] != null && upW > 2 * body && C.h[i] >= C.hod[i] - 0.01) return -1; return 0; }],
  ["n48_beltHold", "Belt-hold line", "PAT", (C, i) => { const a = C.atr[i]; if (a == null) return 0; const rng = C.h[i] - C.l[i]; if (rng < 0.8 * a) return 0; if (Math.abs(C.o[i] - C.l[i]) < 0.1 * rng && C.c[i] > C.o[i] + 0.6 * rng) return 1; if (Math.abs(C.o[i] - C.h[i]) < 0.1 * rng && C.c[i] < C.o[i] - 0.6 * rng) return -1; return 0; }],
  ["n49_twoBarPop", "Two-bar pop after quiet bar", "PAT", (C, i) => { const a = C.atr[i]; if (a == null) return 0; if (C.h[i - 2] - C.l[i - 2] > 0.7 * a) return 0; if (C.c[i] > C.o[i] && C.c[i - 1] > C.o[i - 1] && C.c[i] > C.c[i - 1]) return 1; if (C.c[i] < C.o[i] && C.c[i - 1] < C.o[i - 1] && C.c[i] < C.c[i - 1]) return -1; return 0; }],
  ["n50_starPattern", "Morning/evening star", "PAT", (C, i) => { const a = C.atr[i]; if (a == null) return 0; const big1 = Math.abs(C.c[i - 2] - C.o[i - 2]) > 0.6 * a, smallMid = Math.abs(C.c[i - 1] - C.o[i - 1]) < 0.3 * a; if (!big1 || !smallMid) return 0; if (C.c[i - 2] < C.o[i - 2] && C.c[i] > C.o[i] && C.c[i] > (C.c[i - 2] + C.o[i - 2]) / 2) return 1; if (C.c[i - 2] > C.o[i - 2] && C.c[i] < C.o[i] && C.c[i] < (C.c[i - 2] + C.o[i - 2]) / 2) return -1; return 0; }],
  // ----- session / time -----
  ["n51_first15mom", "First-15m momentum", "TIME", (C, i) => { if (C.mins[i] !== 580 && C.mins[i] !== 585) return 0; if (C.dOpen[i] == null) return 0; if (C.c[i] > C.dOpen[i] && C.c[i] > C.o[i]) return 1; if (C.c[i] < C.dOpen[i] && C.c[i] < C.o[i]) return -1; return 0; }],
  ["n52_tenAmRev", "10:00 first-30m fade to open", "TIME", (C, i) => { if (C.mins[i] < 600 || C.mins[i] > 615 || C.dOpen[i] == null || C.hod[i] == null) return 0; if (C.hod[i] - C.dOpen[i] > C.dOpen[i] - C.lod[i] && C.c[i] < C.o[i]) return -1; if (C.dOpen[i] - C.lod[i] > C.hod[i] - C.dOpen[i] && C.c[i] > C.o[i]) return 1; return 0; }],
  ["n53_afternoonTrend", "Afternoon trend (>14:00)", "TIME", (C, i) => { if (C.mins[i] < 840 || C.mins[i] > 930 || C.vwap[i] == null || C.ema200[i] == null) return 0; if (C.c[i] > C.vwap[i] && C.c[i] > C.ema200[i] && C.c[i] > C.o[i]) return 1; if (C.c[i] < C.vwap[i] && C.c[i] < C.ema200[i] && C.c[i] < C.o[i]) return -1; return 0; }],
  ["n54_lastHrHOD", "Last hour close-near-HOD push", "TIME", (C, i) => { if (C.mins[i] < 900 || C.hod[i] == null) return 0; const rng = C.hod[i] - C.lod[i]; if (rng <= 0) return 0; if (C.c[i] >= C.lod[i] + 0.8 * rng && C.c[i] > C.o[i]) return 1; if (C.c[i] <= C.lod[i] + 0.2 * rng && C.c[i] < C.o[i]) return -1; return 0; }],
  ["n55_lunchFade", "Lunch (12:00-13:30) VWAP fade", "TIME", (C, i) => { if (C.mins[i] < 720 || C.mins[i] > 810 || C.vwap[i] == null) return 0; const a = C.atr[i]; if (a == null) return 0; if (C.c[i] < C.vwap[i] - a && C.c[i] > C.o[i]) return 1; if (C.c[i] > C.vwap[i] + a && C.c[i] < C.o[i]) return -1; return 0; }],
  ["n56_eodRevert", "EOD (>15:30) VWAP revert", "TIME", (C, i) => { if (C.mins[i] < 930 || C.vwap[i] == null || !(C.sd[i] > 0)) return 0; const z = (C.c[i] - C.vwap[i]) / C.sd[i]; if (z < -2) return 1; if (z > 2) return -1; return 0; }],
  ["n57_gapGo", "Gap-and-go momentum", "TIME", (C, i) => { if (C.mins[i] < 585 || C.mins[i] > 615 || C.pdC[i] == null || C.dOpen[i] == null) return 0; const a = C.atr[i]; if (a == null) return 0; if (C.dOpen[i] > C.pdC[i] + 0.5 * a && C.c[i] > C.dOpen[i]) return 1; if (C.dOpen[i] < C.pdC[i] - 0.5 * a && C.c[i] < C.dOpen[i]) return -1; return 0; }],
  ["n58_openDriveBar", "09:30 bar continuation", "TIME", (C, i) => { if (C.mins[i] !== 575) return 0; if (C.c[i - 1] > C.o[i - 1] && C.c[i] > C.h[i - 1]) return 1; if (C.c[i - 1] < C.o[i - 1] && C.c[i] < C.l[i - 1]) return -1; return 0; }],
  // ----- multi-indicator confluence -----
  ["n59_rsiBB", "RSI<30 + below lower band", "CONF", (C, i) => { if (C.rsi14[i] == null || C.bbL[i] == null) return 0; if (C.rsi14[i] < 30 && C.c[i] < C.bbL[i]) return 1; if (C.rsi14[i] > 70 && C.c[i] > C.bbU[i]) return -1; return 0; }],
  ["n60_macdRsi", "MACD>signal + RSI 50-cross", "CONF", (C, i) => { if (C.macd[i] == null || C.rsi14[i] == null || C.rsi14[i - 1] == null) return 0; if (C.macd[i] > C.sig[i] && C.rsi14[i - 1] <= 50 && C.rsi14[i] > 50) return 1; if (C.macd[i] < C.sig[i] && C.rsi14[i - 1] >= 50 && C.rsi14[i] < 50) return -1; return 0; }],
  ["n61_stochMacd", "Stoch turn-up + hist rising", "CONF", (C, i) => { if (C.K[i] == null || C.K[i - 1] == null || C.hist[i] == null) return 0; if (C.K[i - 1] < 20 && C.K[i] > C.K[i - 1] && C.hist[i] > C.hist[i - 1]) return 1; if (C.K[i - 1] > 80 && C.K[i] < C.K[i - 1] && C.hist[i] < C.hist[i - 1]) return -1; return 0; }],
  ["n62_cciAdx", "CCI>100 + ADX>20 rising", "CONF", (C, i) => { if (C.cci[i] == null || !C.adx || C.adx[i] == null || C.adx[i - 1] == null) return 0; if (C.cci[i] > 100 && C.adx[i] > 20 && C.adx[i] > C.adx[i - 1]) return 1; if (C.cci[i] < -100 && C.adx[i] > 20 && C.adx[i] > C.adx[i - 1]) return -1; return 0; }],
  ["n63_obvBreak", "OBV-accumulation new high", "CONF", (C, i) => { if (C.obv[i] == null) return 0; let mx = -Infinity, mn = Infinity; for (let k = 1; k <= 20; k++) { if (C.obv[i - k] == null) return 0; mx = Math.max(mx, C.obv[i - k]); mn = Math.min(mn, C.obv[i - k]); } if (C.obv[i] > mx && C.c[i] > C.o[i]) return 1; if (C.obv[i] < mn && C.c[i] < C.o[i]) return -1; return 0; }],
  ["n64_volFlow", "3-bar up-volume dominance", "CONF", (C, i) => { let up = 0, dn = 0; for (let k = 0; k < 3; k++) { if (C.c[i - k] > C.o[i - k]) up += C.v[i - k] || 1; else dn += C.v[i - k] || 1; } if (up > 2 * dn && C.c[i] > C.c[i - 1]) return 1; if (dn > 2 * up && C.c[i] < C.c[i - 1]) return -1; return 0; }],
  ["n65_keltMomBrk", "Keltner momentum breakout", "CONF", (C, i) => { if (C.keltU[i] == null || C.ema200[i] == null) return 0; if (C.c[i] > C.keltU[i] && C.c[i] > C.ema200[i]) return 1; if (C.c[i] < C.keltL[i] && C.c[i] < C.ema200[i]) return -1; return 0; }],
  ["n66_donMid", "Donchian-20 midline cross", "CONF", (C, i) => { if (C.don20H[i] == null || C.don20L[i] == null || C.don20H[i - 1] == null) return 0; const mid = (C.don20H[i] + C.don20L[i]) / 2, midp = (C.don20H[i - 1] + C.don20L[i - 1]) / 2; if (C.c[i - 1] <= midp && C.c[i] > mid) return 1; if (C.c[i - 1] >= midp && C.c[i] < mid) return -1; return 0; }],
  ["n67_erBreak", "Efficiency-ratio trend break", "CONF", (C, i) => { if (C.er[i] == null || C.don20H[i] == null) return 0; if (C.er[i] > 0.5 && C.c[i] > C.don20H[i]) return 1; if (C.er[i] > 0.5 && C.c[i] < C.don20L[i]) return -1; return 0; }],
  ["n68_choppyFade", "Low-efficiency range fade", "CONF", (C, i) => { if (C.er[i] == null || C.bbL[i] == null) return 0; if (C.er[i] < 0.25) { if (C.l[i] <= C.bbL[i] && C.c[i] > C.bbL[i]) return 1; if (C.h[i] >= C.bbU[i] && C.c[i] < C.bbU[i]) return -1; } return 0; }],
  ["n69_rocAccel", "ROC acceleration", "CONF", (C, i) => { if (C.roc[i] == null || C.roc[i - 2] == null) return 0; if (C.roc[i] > 0 && C.roc[i] > C.roc[i - 1] && C.roc[i - 1] > C.roc[i - 2]) return 1; if (C.roc[i] < 0 && C.roc[i] < C.roc[i - 1] && C.roc[i - 1] < C.roc[i - 2]) return -1; return 0; }],
  ["n70_emaPullback", "EMA20 trend pullback", "CONF", (C, i) => { if (C.ema20[i] == null || C.ema200[i] == null) return 0; if (C.c[i] > C.ema200[i] && C.l[i] <= C.ema20[i] && C.c[i] > C.ema20[i] && C.c[i] > C.o[i]) return 1; if (C.c[i] < C.ema200[i] && C.h[i] >= C.ema20[i] && C.c[i] < C.ema20[i] && C.c[i] < C.o[i]) return -1; return 0; }],
  ["n71_vwapPullback", "VWAP trend pullback bounce", "CONF", (C, i) => { if (C.vwap[i] == null || C.vwap[i - 1] == null) return 0; const a = C.atr[i]; if (a == null) return 0; if (C.c[i - 1] > C.vwap[i - 1] && C.l[i] <= C.vwap[i] + 0.2 * a && C.c[i] > C.vwap[i] && C.c[i] > C.o[i]) return 1; if (C.c[i - 1] < C.vwap[i - 1] && C.h[i] >= C.vwap[i] - 0.2 * a && C.c[i] < C.vwap[i] && C.c[i] < C.o[i]) return -1; return 0; }],
  ["n72_breakRetest", "20-bar break + retest hold", "CONF", (C, i) => { if (C.don20H[i] == null || C.don20H[i - 2] == null) return 0; const a = C.atr[i]; if (a == null) return 0; if (C.c[i - 2] > C.don20H[i - 2] && C.l[i] <= C.don20H[i] + 0.3 * a && C.c[i] > C.don20H[i] && C.c[i] > C.o[i]) return 1; if (C.c[i - 2] < C.don20L[i - 2] && C.h[i] >= C.don20L[i] - 0.3 * a && C.c[i] < C.don20L[i] && C.c[i] < C.o[i]) return -1; return 0; }],
];

// locked champion entry (benchmark) — power hour + EMA200 trend + close trigger + ADX>20
function championDir(C, i) { const m = C.mins[i]; if (m < 900 || m > 945 || C.ema200[i] == null || !C.adx || C.adx[i] == null) return 0; if (C.c[i] > C.ema200[i] && C.c[i] > C.o[i] && C.c[i] > C.c[i - 1] && C.adx[i] > 20) return 1; if (C.c[i] < C.ema200[i] && C.c[i] < C.o[i] && C.c[i] < C.c[i - 1] && C.adx[i] > 20) return -1; return 0; }

// ---------------- evaluate one direction-series with the COMMON exit ----------------
function brk(price, a, dir) { return dir === 1 ? { dir: 1, entry: price, stop: price - STOP_MULT * a, target: price + TGT_MULT * a } : { dir: -1, entry: price, stop: price + STOP_MULT * a, target: price - TGT_MULT * a }; }
function evalDir(bars, C, dirAt) {
  const sig = new Array(bars.length).fill(null); let err = 0;
  for (let i = 210; i < bars.length; i++) {
    const a = C.atr[i]; if (a == null || !(a > 0)) continue;
    let d = 0; try { d = dirAt(i) || 0; } catch (e) { err++; continue; }
    if (d === 1 || d === -1) sig[i] = brk(C.c[i], a, d);
  }
  const ledger = Lab.runLedger(bars, sig); const t = Lab.tally(ledger);
  const net$ = t.netPts * DPP, dd$ = t.ddPts * DPP, wd$ = Math.abs(t.worstDayPts) * DPP;
  return { n: t.n, win: +t.winRate.toFixed(1), pf: t.pf === Infinity ? 99 : +t.pf.toFixed(2), netPts: +t.netPts.toFixed(1), net$: Math.round(net$), dd$: Math.round(dd$), wd$: Math.round(wd$), mls: t.maxLossStreak, exp: t.n ? +(t.netPts / t.n).toFixed(2) : 0, feasible: wd$ < DLL && dd$ < MLL, err };
}

function loadJson(p) { return JSON.parse(fs.readFileSync(p, "utf8")).filter((b) => b && isFinite(b.c)).sort((a, b) => a.t - b.t); }
function spanOf(bars) { return [bars[0].t, bars[bars.length - 1].t].map((s) => new Date(s * 1000).toISOString().slice(0, 10)); }

function main() {
  const t0 = Date.now();
  console.log("CATALOG-13 — distinct-METHOD screen. One common exit (1.2/1.8 ATR) for ALL, so only the ENTRY edge varies.");

  let bars13 = null, span13 = null, days13 = 0;
  try { bars13 = Lab.loadCsv(Lab.CSV_13); span13 = spanOf(bars13); days13 = new Set(bars13.map((b) => dkOf(b.t))).size; } catch (e) { console.log("13-day CSV unavailable: " + e.message); }
  const bars58 = loadJson(path.join(__dirname, "data", "nq-5m.json"));
  const span58 = spanOf(bars58), days58 = new Set(bars58.map((b) => dkOf(b.t))).size;
  if (bars13) console.log(`13d chart: ${bars13.length} bars, ${days13} days, ${span13[0]} -> ${span13[1]}  (PRIMARY)`);
  console.log(`58d chart: ${bars58.length} bars, ${days58} days, ${span58[0]} -> ${span58[1]}  (confirmation)`);

  function methodsFor(bars) {
    const C = ctxOf(bars), S = Lab.buildAll(bars), out = [];
    for (const k of Lab.KEYS) out.push({ key: "lab_" + k, name: Lab.NAMES[k], cat: "lab50", dirAt: (i) => (S[k][i] ? S[k][i].dir : 0) });
    for (const [key, name, cat, fn] of NEW) out.push({ key, name, cat, dirAt: (i) => fn(C, i) });
    out.push({ key: "CHAMPION", name: "* Champion (PH+EMA200+ADX>20)", cat: "champ", dirAt: (i) => championDir(C, i) });
    return { C, methods: out };
  }

  const prime = bars13 || bars58;
  const primeName = bars13 ? "13d" : "58d";
  const pm = methodsFor(prime);
  const cm = methodsFor(bars58);
  const cmMap = new Map(cm.methods.map((m) => [m.key, m]));

  const results = pm.methods.map((m) => {
    const P = evalDir(prime, pm.C, m.dirAt);
    const conf = cmMap.get(m.key);
    const A = conf ? evalDir(bars58, cm.C, conf.dirAt) : null;
    return { key: m.key, name: m.name, cat: m.cat, P, A };
  });
  results.sort((a, b) => b.P.netPts - a.P.netPts);
  results.forEach((r, i) => r.rank = i + 1);

  const errs = results.filter((r) => r.P.err > 0).map((r) => r.key);
  const champ = results.find((r) => r.key === "CHAMPION");

  const dol = (n) => (n >= 0 ? "+$" : "-$") + Math.abs(n);
  console.log(`\nField: ${results.length} distinct methods | ranked on ${primeName} net | both columns use the SAME 1.2/1.8 ATR exit. $ @5 MNQ.`);
  const hdr = "#".padStart(4) + "  " + "Method".padEnd(34) + "Cat".padEnd(7) + "Trd".padStart(4) + "Win%".padStart(6) + "PF".padStart(6) + ("Net" + primeName).padStart(9) + "WrstDay".padStart(9) + "feas".padStart(5) + "  58dNet".padStart(10) + "58dPF".padStart(7);
  console.log(hdr); console.log("-".repeat(hdr.length));
  for (const r of results.slice(0, 30)) {
    console.log(String(r.rank).padStart(4) + "  " + r.name.slice(0, 33).padEnd(34) + r.cat.padEnd(7) + String(r.P.n).padStart(4) + (r.P.win + "%").padStart(6) + String(r.P.pf).padStart(6) + dol(r.P.net$).padStart(9) + ("-$" + r.P.wd$).padStart(9) + (r.P.feasible ? "ok" : "DD!").padStart(5) + "  " + (r.A ? dol(r.A.net$).padStart(8) + String(r.A.pf).padStart(7) : "   n/a"));
  }
  console.log(`\n* Champion ranks #${champ.rank} of ${results.length} on ${primeName}: ${champ.P.n} trades, ${champ.P.win}% win, PF ${champ.P.pf}, ${dol(champ.P.net$)} (58d ${dol(champ.A.net$)}).`);
  if (errs.length) console.log(`Methods that errored (treated as no-signal): ${errs.join(", ")}`);

  const robust = results.filter((r) => r.P.net$ > 0 && r.A && r.A.net$ > 0 && r.P.feasible && r.P.n >= 4);
  console.log(`\nRobust shortlist (net>0 on BOTH 13d & 58d, feasible, >=4 trades): ${robust.length}`);
  for (const r of robust.slice(0, 15)) console.log(`   #${r.rank} ${r.name} - ${primeName} ${dol(r.P.net$)} (${r.P.n}t ${r.P.win}%) | 58d ${dol(r.A.net$)} (${r.A.n}t ${r.A.win}%)`);

  fs.writeFileSync(OUT_JSON, JSON.stringify({ generatedAt: new Date().toISOString(), exit: { stopMultATR: STOP_MULT, targetMultATR: TGT_MULT }, prime: primeName, span13, span58, fieldSize: results.length, champRank: champ.rank, robustCount: robust.length, results }, null, 2));
  const md = [];
  md.push(`# Catalog-13 - distinct-method screen (${new Date().toISOString().slice(0, 10)})`);
  md.push(`\n**${results.length} genuinely distinct entry methods**, all forced through ONE common exit (stop ${STOP_MULT}x ATR / target ${TGT_MULT}x ATR, RTH, flat by 16:00, one-at-a-time). Only the ENTRY edge varies - no per-method stop/target/gate tuning. Champion included as benchmark (NOT replaced).`);
  md.push(`\nRanked on **${primeName}** (${bars13 ? span13.join(" -> ") : span58.join(" -> ")}). 58-day NQ column = robustness confirmation. Dollars @5 MNQ.`);
  md.push(`\n- Champion rank: **#${champ.rank} of ${results.length}** on ${primeName} (${dol(champ.P.net$)}; 58d ${dol(champ.A.net$)}).`);
  md.push(`- Robust shortlist (net>0 on BOTH samples, feasible, >=4 trades): **${robust.length}**.`);
  md.push(`\n> WARNING: 13 days is a SCREEN, not proof. Most methods fire only a handful of times here - high overfit/noise risk. A method only matters if it also holds on the 58-day column and out-of-sample. Gross only (no slippage/commissions).`);
  md.push(`\n## Top 30 on ${primeName}\n`);
  md.push(`| # | Method | Cat | Trd | Win% | PF | Net(${primeName}) | WorstDay | Feasible | 58d Net | 58d PF |`);
  md.push(`|---|--------|-----|----:|-----:|---:|------:|------:|:--:|------:|---:|`);
  for (const r of results.slice(0, 30)) md.push(`| ${r.rank} | ${r.name} | ${r.cat} | ${r.P.n} | ${r.P.win} | ${r.P.pf} | ${dol(r.P.net$)} | -$${r.P.wd$} | ${r.P.feasible ? "yes" : "DD!"} | ${r.A ? dol(r.A.net$) : "n/a"} | ${r.A ? r.A.pf : "n/a"} |`);
  md.push(`\n## Robust shortlist (held up on both samples)\n`);
  if (robust.length) { md.push(`| # | Method | ${primeName} Net | ${primeName} Trd/Win | 58d Net | 58d Trd/Win |`); md.push(`|---|--------|------:|:--:|------:|:--:|`); for (const r of robust) md.push(`| ${r.rank} | ${r.name} | ${dol(r.P.net$)} | ${r.P.n}/${r.P.win}% | ${dol(r.A.net$)} | ${r.A.n}/${r.A.win}% |`); }
  else md.push(`_None cleared the bar - unsurprising on 13 days. Re-screen on the 58-day as primary for a real read._`);
  fs.writeFileSync(OUT_MD, md.join("\n") + "\n");

  console.log(`\nSaved ${OUT_JSON} and ${OUT_MD}. (${((Date.now() - t0) / 1000).toFixed(1)}s)`);
  console.log("DATA-ONLY: live bot + champion.json untouched.");
}

// Reusable building blocks for optimize10.js (entry methods + context).
module.exports = { ctxOf, NEW, championDir, STOP_MULT, TGT_MULT };

if (require.main === module) main();
