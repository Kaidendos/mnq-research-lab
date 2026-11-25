// =============================================================
//  strat-gen.js — generate & screen 150 candidate strategies.
//
//  Built after the power-hour post-mortem (0-for-11 live: every entry was a
//  momentum-chase faded in chop) + the QuantRepublic [WICK] example (a
//  liquidity-sweep / FVG-retest reversal with a tight stop and high RR).
//  Lesson encoded here: bias toward REVERSAL / SWEEP / FVG / mean-revert
//  edges and test HIGHER reward:risk, not just breakout-chasing.
//
//  150 = 50 distinct ENTRY edges  x  3 reward:risk EXIT profiles.
//  Each entry returns -1|0|+1 at a bar; the exit profile turns it into an
//  ATR bracket. NO time-of-day limit (entries any RTH bar) — per request.
//  Every strategy is backtested on TWO datasets and only the ones that hold
//  up on BOTH (out-of-sample) survive.
//
//    13d = CSV_13  (cached MNQ 5m TradingView export)  — PRIMARY
//    58d = data/nq-5m.json (cached NQ=F 5m)            — confirmation
//
//  DATA-ONLY / TopStep-compliant: reads local data, places no orders.
//  Run:  node strat-gen.js
// =============================================================
"use strict";
const fs = require("fs");
const path = require("path");
require("./public/indicators.js");
const I = globalThis.Indicators;
const Lab = require("./lab-new4.js");
const ep = Lab.etParts, dkOf = Lab.dayKeyOf;

const PV = 2, CONTRACTS = 5, DPP = PV * CONTRACTS; // $/pt @ 5 MNQ = 10
const DLL = 1000, MLL = 2000;                      // Combine daily-loss / trailing-DD walls
const RTH_START = 570, RTH_END = 960;
const OUT_MD = path.join(__dirname, "logs", "strat150-report.md");
const OUT_JSON = path.join(__dirname, "logs", "strat150-results.json");

// ---- 3 exit profiles (ATR multiples). RR rises L->R per the high-RR lesson ----
const EXITS = [
  { tag: "RR1.5", s: 1.2, t: 1.8 },
  { tag: "RR3",   s: 1.0, t: 3.0 },
  { tag: "RR5",   s: 0.7, t: 3.5 },
];

// ---------------- standalone indicator helpers ----------------
function priorMax(a, n) { const o = Array(a.length).fill(null); for (let i = n; i < a.length; i++) { let m = -Infinity; for (let k = i - n; k < i; k++) m = Math.max(m, a[k]); o[i] = m; } return o; }
function priorMin(a, n) { const o = Array(a.length).fill(null); for (let i = n; i < a.length; i++) { let m = Infinity; for (let k = i - n; k < i; k++) m = Math.min(m, a[k]); o[i] = m; } return o; }
function stochK(h, l, c, n) { const K = Array(c.length).fill(null); for (let i = n - 1; i < c.length; i++) { let hh = -Infinity, ll = Infinity; for (let k = i - n + 1; k <= i; k++) { hh = Math.max(hh, h[k]); ll = Math.min(ll, l[k]); } K[i] = hh > ll ? (c[i] - ll) / (hh - ll) * 100 : 50; } return K; }
function cciCalc(h, l, c, n) { const tp = h.map((x, i) => (x + l[i] + c[i]) / 3), ma = I.sma(tp, n), o = Array(c.length).fill(null); for (let i = n - 1; i < c.length; i++) { let md = 0; for (let k = i - n + 1; k <= i; k++) md += Math.abs(tp[k] - ma[i]); md /= n; o[i] = md === 0 ? 0 : (tp[i] - ma[i]) / (0.015 * md); } return o; }
function lastSwing(arr, isHigh, lft, rgt) { const n = arr.length, o = Array(n).fill(null); let last = null; for (let i = 0; i < n; i++) { const c = i - rgt; if (c >= lft) { let piv = true; for (let k = 1; k <= lft && piv; k++) if (isHigh ? arr[c - k] > arr[c] : arr[c - k] < arr[c]) piv = false; for (let k = 1; k <= rgt && piv; k++) if (isHigh ? arr[c + k] > arr[c] : arr[c + k] < arr[c]) piv = false; if (piv) last = arr[c]; } o[i] = last; } return o; }
// RTH-anchored VWAP + running sigma; running session HOD/LOD/open; prior-day HLC; opening-range
function sessionStuff(bars) {
  const N = bars.length;
  const vwap = Array(N).fill(null), sd = Array(N).fill(null);
  const hod = Array(N).fill(null), lod = Array(N).fill(null), dOpen = Array(N).fill(null);
  const pdH = Array(N).fill(null), pdL = Array(N).fill(null), pdC = Array(N).fill(null);
  const orH = Array(N).fill(null), orL = Array(N).fill(null);
  const order = [], H = new Map(), L = new Map(), C = new Map();
  let cur = null, vN = 0, vD = 0, vN2 = 0, hi = -Infinity, lo = Infinity, op = null, lastC = null;
  let curORh = -Infinity, curORl = Infinity;
  for (let i = 0; i < N; i++) {
    const p = ep(bars[i].t), b = bars[i];
    if (p.k !== cur) {
      if (cur != null) { H.set(cur, hi); L.set(cur, lo); C.set(cur, lastC); order.push(cur); }
      cur = p.k; vN = vD = vN2 = 0; hi = -Infinity; lo = Infinity; op = null; curORh = -Infinity; curORl = Infinity;
    }
    const inR = p.day !== 0 && p.day !== 6 && p.mins >= RTH_START && p.mins < RTH_END;
    if (inR) {
      if (op == null) op = b.o;
      hi = Math.max(hi, b.h); lo = Math.min(lo, b.l); lastC = b.c;
      const hlc3 = (b.h + b.l + b.c) / 3, v = b.v || 1;
      vN += hlc3 * v; vN2 += hlc3 * hlc3 * v; vD += v;
      if (p.mins < RTH_START + 30) { curORh = Math.max(curORh, b.h); curORl = Math.min(curORl, b.l); } // first 30m
    }
    if (vD > 0) { const m = vN / vD; vwap[i] = m; sd[i] = Math.sqrt(Math.max(0, vN2 / vD - m * m)); }
    hod[i] = hi === -Infinity ? null : hi; lod[i] = lo === Infinity ? null : lo; dOpen[i] = op;
    orH[i] = curORh === -Infinity ? null : curORh; orL[i] = curORl === Infinity ? null : curORl;
    // prior-day HLC = the most recently completed day before today
    const idx = order.length - 1;
    if (idx >= 0) { pdH[i] = H.get(order[idx]); pdL[i] = L.get(order[idx]); pdC[i] = C.get(order[idx]); }
  }
  return { vwap, sd, hod, lod, dOpen, pdH, pdL, pdC, orH, orL };
}

function buildContext(bars) {
  const o = bars.map(b => b.o), h = bars.map(b => b.h), l = bars.map(b => b.l), c = bars.map(b => b.c), v = bars.map(b => b.v || 0);
  const dmi = I.dmi(h, l, c, 14, 14);
  const { macdLine, signalLine } = I.macd(c, 12, 26, 9);
  const dev = I.stdev(c, 20), sma20 = I.sma(c, 20);
  const bbU = sma20.map((m, i) => m == null || dev[i] == null ? null : m + 2 * dev[i]);
  const bbL = sma20.map((m, i) => m == null || dev[i] == null ? null : m - 2 * dev[i]);
  const pctB = c.map((x, i) => bbU[i] == null || bbU[i] === bbL[i] ? null : (x - bbL[i]) / (bbU[i] - bbL[i]));
  const ss = sessionStuff(bars);
  return {
    o, h, l, c, v,
    atr: I.atr(h, l, c, 14),
    ema9: I.ema(c, 9), ema20: I.ema(c, 20), ema21: I.ema(c, 21), ema50: I.ema(c, 50), ema200: I.ema(c, 200),
    sma20, rsi2: I.rsi(c, 2), rsi14: I.rsi(c, 14),
    adx: dmi.adx, macdLine, signalLine, dev, bbU, bbL, pctB,
    K: stochK(h, l, c, 14), cci: cciCalc(h, l, c, 20),
    don20H: priorMax(h, 20), don20L: priorMin(l, 20), don55H: priorMax(h, 55), don55L: priorMin(l, 55),
    swingH: lastSwing(h, true, 3, 3), swingL: lastSwing(l, false, 3, 3),
    swingH2: lastSwing(h, true, 2, 2), swingL2: lastSwing(l, false, 2, 2),
    ...ss,
    mins: bars.map(b => ep(b.t).mins),
  };
}
const xUp = (a, b, i) => a[i - 1] != null && b[i - 1] != null && a[i - 1] <= b[i - 1] && a[i] > b[i];
const xDn = (a, b, i) => a[i - 1] != null && b[i - 1] != null && a[i - 1] >= b[i - 1] && a[i] < b[i];
const body = (C, i) => Math.abs(C.c[i] - C.o[i]);
const upWick = (C, i) => C.h[i] - Math.max(C.o[i], C.c[i]);
const dnWick = (C, i) => Math.min(C.o[i], C.c[i]) - C.l[i];

// ---- bullish/bearish FVG retest within a small window ----
function fvgDir(C, i, W, gMul) {
  const a = C.atr[i]; if (a == null) return 0;
  for (let j = i - 1; j >= i - W; j--) {
    if (j - 2 < 0) break;
    // bullish gap formed at j: low[j] > high[j-2]
    if (C.l[j] > C.h[j - 2] && C.l[j] - C.h[j - 2] >= gMul * a) {
      const top = C.l[j], bot = C.h[j - 2];
      if (C.l[i] <= top && C.l[i] >= bot && C.c[i] > C.o[i]) return 1; // retraced into gap, rejected up
    }
    // bearish gap: high[j] < low[j-2]
    if (C.h[j] < C.l[j - 2] && C.l[j - 2] - C.h[j] >= gMul * a) {
      const bot = C.h[j], top = C.l[j - 2];
      if (C.h[i] >= bot && C.h[i] <= top && C.c[i] < C.o[i]) return -1;
    }
  }
  return 0;
}

// ================= 50 distinct ENTRY edges: fn(C,i) -> -1|0|1 =================
// cat: SWEEP/FVG/REV/MR/VOL/MOM/BRK/TIME — first five are the lesson-favored families.
const ENTRIES = [
  // ---------- FVG / imbalance retest (from the [WICK] example) ----------
  ["fvg_w4_g02", "FVG retest (win4, gap.2ATR)", "FVG", (C, i) => fvgDir(C, i, 4, 0.2)],
  ["fvg_w6_g02", "FVG retest (win6, gap.2ATR)", "FVG", (C, i) => fvgDir(C, i, 6, 0.2)],
  ["fvg_w6_g04", "FVG retest (win6, gap.4ATR)", "FVG", (C, i) => fvgDir(C, i, 6, 0.4)],
  ["fvg_w8_g03", "FVG retest (win8, gap.3ATR)", "FVG", (C, i) => fvgDir(C, i, 8, 0.3)],
  ["fvg_trend", "FVG retest + EMA50 trend", "FVG", (C, i) => { const d = fvgDir(C, i, 6, 0.2); if (!d || C.ema50[i] == null) return 0; if (d === 1 && C.c[i] > C.ema50[i]) return 1; if (d === -1 && C.c[i] < C.ema50[i]) return -1; return 0; }],
  // ---------- liquidity sweep + reclaim (the "stop-grab then push" you described) ----------
  ["sweep_swing3", "Sweep swing(3,3) + reclaim", "SWEEP", (C, i) => { const sl = C.swingL[i], sh = C.swingH[i]; if (sl != null && C.l[i] < sl && C.c[i] > sl && C.c[i] > C.o[i]) return 1; if (sh != null && C.h[i] > sh && C.c[i] < sh && C.c[i] < C.o[i]) return -1; return 0; }],
  ["sweep_swing2", "Sweep swing(2,2) + reclaim", "SWEEP", (C, i) => { const sl = C.swingL2[i], sh = C.swingH2[i]; if (sl != null && C.l[i] < sl && C.c[i] > sl && C.c[i] > C.o[i]) return 1; if (sh != null && C.h[i] > sh && C.c[i] < sh && C.c[i] < C.o[i]) return -1; return 0; }],
  ["sweep_don20", "Sweep Donchian-20 + reclaim", "SWEEP", (C, i) => { if (C.don20L[i] == null) return 0; if (C.l[i] < C.don20L[i] && C.c[i] > C.don20L[i] && C.c[i] > C.o[i]) return 1; if (C.h[i] > C.don20H[i] && C.c[i] < C.don20H[i] && C.c[i] < C.o[i]) return -1; return 0; }],
  ["sweep_pdl", "Sweep prior-day H/L + reclaim", "SWEEP", (C, i) => { if (C.pdL[i] == null) return 0; if (C.l[i] <= C.pdL[i] && C.c[i] > C.pdL[i] && C.c[i] > C.o[i]) return 1; if (C.h[i] >= C.pdH[i] && C.c[i] < C.pdH[i] && C.c[i] < C.o[i]) return -1; return 0; }],
  ["sweep_sess", "Sweep session H/L + reclaim", "SWEEP", (C, i) => { const pl = C.lod[i - 1], ph = C.hod[i - 1]; if (pl == null) return 0; if (C.l[i] < pl && C.c[i] > pl && C.c[i] > C.o[i]) return 1; if (C.h[i] > ph && C.c[i] < ph && C.c[i] < C.o[i]) return -1; return 0; }],
  ["sweep_open", "Sweep day-open reclaim", "SWEEP", (C, i) => { if (C.dOpen[i] == null) return 0; if (C.l[i] < C.dOpen[i] && C.c[i] > C.dOpen[i] && C.c[i] > C.o[i]) return 1; if (C.h[i] > C.dOpen[i] && C.c[i] < C.dOpen[i] && C.c[i] < C.o[i]) return -1; return 0; }],
  // ---------- wick rejection / pin bar at a level ----------
  ["pin_2x", "Pin bar (wick 2x body)", "REV", (C, i) => { const b = body(C, i) || 1e-9, rng = C.h[i] - C.l[i] || 1e-9; if (dnWick(C, i) >= 2 * b && (C.c[i] - C.l[i]) / rng > 0.66) return 1; if (upWick(C, i) >= 2 * b && (C.h[i] - C.c[i]) / rng > 0.66) return -1; return 0; }],
  ["pin_ema50", "Pin bar at EMA50", "REV", (C, i) => { const b = body(C, i) || 1e-9; if (C.ema50[i] == null) return 0; if (dnWick(C, i) >= 1.5 * b && C.l[i] <= C.ema50[i] && C.c[i] > C.ema50[i]) return 1; if (upWick(C, i) >= 1.5 * b && C.h[i] >= C.ema50[i] && C.c[i] < C.ema50[i]) return -1; return 0; }],
  ["pin_vwap", "Pin bar at VWAP", "REV", (C, i) => { const b = body(C, i) || 1e-9; if (C.vwap[i] == null) return 0; if (dnWick(C, i) >= 1.5 * b && C.l[i] <= C.vwap[i] && C.c[i] > C.vwap[i]) return 1; if (upWick(C, i) >= 1.5 * b && C.h[i] >= C.vwap[i] && C.c[i] < C.vwap[i]) return -1; return 0; }],
  ["climax_fade", "Climax bar (>3xATR) fade", "REV", (C, i) => { const a = C.atr[i]; if (a == null) return 0; const rng = C.h[i] - C.l[i]; if (rng < 3 * a) return 0; if (C.c[i] <= C.l[i] + 0.33 * rng) return 1; if (C.c[i] >= C.h[i] - 0.33 * rng) return -1; return 0; }],
  ["key_rev", "Key reversal bar", "REV", (C, i) => { let nl = true, nh = true; for (let k = 1; k <= 5; k++) { if (C.l[i] >= C.l[i - k]) nl = false; if (C.h[i] <= C.h[i - k]) nh = false; } if (nl && C.c[i] > C.o[i] && C.c[i] > C.c[i - 1]) return 1; if (nh && C.c[i] < C.o[i] && C.c[i] < C.c[i - 1]) return -1; return 0; }],
  ["engulf_trend", "Engulfing w/ EMA50 trend", "REV", (C, i) => { if (C.ema50[i] == null) return 0; const bull = C.c[i] > C.o[i] && C.c[i] >= C.h[i - 1] && C.o[i] <= C.l[i - 1]; const bear = C.c[i] < C.o[i] && C.c[i] <= C.l[i - 1] && C.o[i] >= C.h[i - 1]; if (bull && C.c[i] > C.ema50[i]) return 1; if (bear && C.c[i] < C.ema50[i]) return -1; return 0; }],
  ["three_down", "Three down-closes bounce", "REV", (C, i) => { const dn = C.c[i - 1] < C.c[i - 2] && C.c[i - 2] < C.c[i - 3], up = C.c[i - 1] > C.c[i - 2] && C.c[i - 2] > C.c[i - 3]; if (dn && C.c[i] > C.o[i]) return 1; if (up && C.c[i] < C.o[i]) return -1; return 0; }],
  // ---------- VWAP reclaim / retest ----------
  ["vwap_reclaim", "VWAP reclaim cross", "MR", (C, i) => { if (C.vwap[i] == null) return 0; if (xUp(C.c, C.vwap, i)) return 1; if (xDn(C.c, C.vwap, i)) return -1; return 0; }],
  ["vwap_retest", "VWAP reclaim + retest hold", "MR", (C, i) => { if (C.vwap[i] == null || !(C.sd[i] > 0)) return 0; const near = Math.abs(C.l[i] - C.vwap[i]) <= 0.5 * C.sd[i]; const nearU = Math.abs(C.h[i] - C.vwap[i]) <= 0.5 * C.sd[i]; if (C.c[i] > C.vwap[i] && near && C.c[i] > C.o[i] && C.c[i - 1] > C.vwap[i]) return 1; if (C.c[i] < C.vwap[i] && nearU && C.c[i] < C.o[i] && C.c[i - 1] < C.vwap[i]) return -1; return 0; }],
  ["vwap_2sig", "VWAP 2-sigma fade", "MR", (C, i) => { if (C.vwap[i] == null || !(C.sd[i] > 0)) return 0; const z = (C.c[i] - C.vwap[i]) / C.sd[i]; if (z <= -2 && C.c[i] > C.o[i]) return 1; if (z >= 2 && C.c[i] < C.o[i]) return -1; return 0; }],
  // ---------- mean reversion ----------
  ["rsi2_conn", "Connors RSI(2)+EMA200", "MR", (C, i) => { if (C.rsi2[i] == null || C.ema200[i] == null) return 0; if (C.rsi2[i] < 10 && C.c[i] > C.ema200[i]) return 1; if (C.rsi2[i] > 90 && C.c[i] < C.ema200[i]) return -1; return 0; }],
  ["rsi2_x", "RSI(2) extreme fade", "MR", (C, i) => { if (C.rsi2[i] == null) return 0; if (C.rsi2[i] < 5) return 1; if (C.rsi2[i] > 95) return -1; return 0; }],
  ["bb_reclaim", "Bollinger %B reclaim", "MR", (C, i) => { if (C.pctB[i] == null || C.pctB[i - 1] == null) return 0; if (C.pctB[i - 1] < 0 && C.pctB[i] >= 0) return 1; if (C.pctB[i - 1] > 1 && C.pctB[i] <= 1) return -1; return 0; }],
  ["bb_tag", "BB tag + reject", "MR", (C, i) => { if (C.bbL[i] == null) return 0; if (C.l[i] <= C.bbL[i] && C.c[i] > C.bbL[i] && C.c[i] > C.o[i]) return 1; if (C.h[i] >= C.bbU[i] && C.c[i] < C.bbU[i] && C.c[i] < C.o[i]) return -1; return 0; }],
  ["zscore_2", "Z-score(2) fade", "MR", (C, i) => { if (C.sma20[i] == null || !(C.dev[i] > 0)) return 0; const z = (C.c[i] - C.sma20[i]) / C.dev[i]; if (z <= -2 && C.c[i] > C.o[i]) return 1; if (z >= 2 && C.c[i] < C.o[i]) return -1; return 0; }],
  ["zscore_25", "Z-score(2.5) fade", "MR", (C, i) => { if (C.sma20[i] == null || !(C.dev[i] > 0)) return 0; const z = (C.c[i] - C.sma20[i]) / C.dev[i]; if (z <= -2.5) return 1; if (z >= 2.5) return -1; return 0; }],
  ["cci_zero", "CCI zero-cross + EMA200", "MR", (C, i) => { if (C.cci[i] == null || C.cci[i - 1] == null || C.ema200[i] == null) return 0; if (C.cci[i - 1] < 0 && C.cci[i] >= 0 && C.c[i] > C.ema200[i]) return 1; if (C.cci[i - 1] > 0 && C.cci[i] <= 0 && C.c[i] < C.ema200[i]) return -1; return 0; }],
  ["stoch_x", "Stochastic 20/80 cross", "MR", (C, i) => { if (C.K[i] == null || C.K[i - 1] == null) return 0; if (C.K[i - 1] < 20 && C.K[i] >= 20) return 1; if (C.K[i - 1] > 80 && C.K[i] <= 80) return -1; return 0; }],
  ["rsi14_band", "RSI(14) 30/70 reclaim", "MR", (C, i) => { if (C.rsi14[i] == null || C.rsi14[i - 1] == null) return 0; if (C.rsi14[i - 1] < 30 && C.rsi14[i] >= 30) return 1; if (C.rsi14[i - 1] > 70 && C.rsi14[i] <= 70) return -1; return 0; }],
  ["pdl_tag", "Prior-day low tag bounce", "MR", (C, i) => { if (C.pdL[i] == null) return 0; if (C.l[i] <= C.pdL[i] && C.c[i] > C.pdL[i]) return 1; if (C.h[i] >= C.pdH[i] && C.c[i] < C.pdH[i]) return -1; return 0; }],
  // ---------- volatility contraction / squeeze ----------
  ["nr4", "NR4 narrow-range break", "VOL", (C, i) => { let nr = true; for (let k = 1; k <= 3; k++) if ((C.h[i - 1] - C.l[i - 1]) >= (C.h[i - 1 - k] - C.l[i - 1 - k])) nr = false; if (!nr) return 0; if (C.c[i] > C.h[i - 1]) return 1; if (C.c[i] < C.l[i - 1]) return -1; return 0; }],
  ["nr7", "NR7 narrow-range break", "VOL", (C, i) => { let nr = true; for (let k = 1; k <= 6; k++) if ((C.h[i - 1] - C.l[i - 1]) >= (C.h[i - 1 - k] - C.l[i - 1 - k])) nr = false; if (!nr) return 0; if (C.c[i] > C.h[i - 1]) return 1; if (C.c[i] < C.l[i - 1]) return -1; return 0; }],
  ["squeeze", "BB-width squeeze release", "VOL", (C, i) => { if (C.bbU[i] == null) return 0; const w = C.bbU[i] - C.bbL[i]; let mn = Infinity; for (let k = 0; k < 50; k++) { if (C.bbU[i - k] == null) return 0; mn = Math.min(mn, C.bbU[i - k] - C.bbL[i - k]); } if (w > 1.1 * mn) return 0; if (C.c[i] > C.o[i] && C.c[i] > C.sma20[i]) return 1; if (C.c[i] < C.o[i] && C.c[i] < C.sma20[i]) return -1; return 0; }],
  ["inside_brk", "Inside-bar break", "VOL", (C, i) => { const ins = C.h[i - 1] <= C.h[i - 2] && C.l[i - 1] >= C.l[i - 2]; if (!ins) return 0; if (C.c[i] > C.h[i - 1]) return 1; if (C.c[i] < C.l[i - 1]) return -1; return 0; }],
  ["doji_brk", "Doji-range break", "VOL", (C, i) => { const a = C.atr[i]; if (a == null) return 0; if (body(C, i - 1) > 0.15 * a) return 0; if (C.c[i] > C.h[i - 1]) return 1; if (C.c[i] < C.l[i - 1]) return -1; return 0; }],
  // ---------- breakouts / opening range ----------
  ["don20_brk", "Donchian-20 break", "BRK", (C, i) => { if (C.don20H[i] == null) return 0; if (C.c[i] > C.don20H[i]) return 1; if (C.c[i] < C.don20L[i]) return -1; return 0; }],
  ["don55_brk", "Donchian-55 break", "BRK", (C, i) => { if (C.don55H[i] == null) return 0; if (C.c[i] > C.don55H[i]) return 1; if (C.c[i] < C.don55L[i]) return -1; return 0; }],
  ["or30_brk", "Opening-range(30m) break", "BRK", (C, i) => { if (C.orH[i] == null || C.mins[i] < RTH_START + 30) return 0; if (C.c[i] > C.orH[i] && C.c[i - 1] <= C.orH[i - 1]) return 1; if (C.c[i] < C.orL[i] && C.c[i - 1] >= C.orL[i - 1]) return -1; return 0; }],
  ["pdh_brk", "Prior-day H/L break", "BRK", (C, i) => { if (C.pdH[i] == null) return 0; if (C.c[i] > C.pdH[i] && C.c[i - 1] <= C.pdH[i]) return 1; if (C.c[i] < C.pdL[i] && C.c[i - 1] >= C.pdL[i]) return -1; return 0; }],
  ["swing_brk", "Swing high/low break", "BRK", (C, i) => { if (C.swingH[i] == null) return 0; if (C.c[i] > C.swingH[i] && C.c[i - 1] <= C.swingH[i]) return 1; if (C.c[i] < C.swingL[i] && C.c[i - 1] >= C.swingL[i]) return -1; return 0; }],
  // ---------- momentum / trend (kept for contrast; lessons say weak in chop) ----------
  ["ema9_21", "EMA9/EMA21 cross", "MOM", (C, i) => { if (xUp(C.ema9, C.ema21, i)) return 1; if (xDn(C.ema9, C.ema21, i)) return -1; return 0; }],
  ["ema20_50", "EMA20/EMA50 cross", "MOM", (C, i) => { if (xUp(C.ema20, C.ema50, i)) return 1; if (xDn(C.ema20, C.ema50, i)) return -1; return 0; }],
  ["macd_zero", "MACD zero-line cross", "MOM", (C, i) => { if (C.macdLine[i] == null || C.macdLine[i - 1] == null) return 0; if (C.macdLine[i - 1] <= 0 && C.macdLine[i] > 0) return 1; if (C.macdLine[i - 1] >= 0 && C.macdLine[i] < 0) return -1; return 0; }],
  ["macd_sig", "MACD signal cross", "MOM", (C, i) => { if (xUp(C.macdLine, C.signalLine, i)) return 1; if (xDn(C.macdLine, C.signalLine, i)) return -1; return 0; }],
  ["adx_trend", "ADX>20 + EMA200 momentum", "MOM", (C, i) => { if (C.adx[i] == null || C.ema200[i] == null || C.adx[i] <= 20) return 0; if (C.c[i] > C.ema200[i] && C.c[i] > C.o[i] && C.c[i] > C.c[i - 1]) return 1; if (C.c[i] < C.ema200[i] && C.c[i] < C.o[i] && C.c[i] < C.c[i - 1]) return -1; return 0; }],
  ["pullback_20", "EMA20 pullback in trend", "MOM", (C, i) => { if (C.ema20[i] == null || C.ema50[i] == null) return 0; if (C.ema20[i] > C.ema50[i] && C.l[i] <= C.ema20[i] && C.c[i] > C.ema20[i]) return 1; if (C.ema20[i] < C.ema50[i] && C.h[i] >= C.ema20[i] && C.c[i] < C.ema20[i]) return -1; return 0; }],
  ["three_up", "Three soldiers/crows", "MOM", (C, i) => { const up = C.c[i] > C.o[i] && C.c[i - 1] > C.o[i - 1] && C.c[i - 2] > C.o[i - 2] && C.c[i] > C.c[i - 1] && C.c[i - 1] > C.c[i - 2]; const dn = C.c[i] < C.o[i] && C.c[i - 1] < C.o[i - 1] && C.c[i - 2] < C.o[i - 2] && C.c[i] < C.c[i - 1] && C.c[i - 1] < C.c[i - 2]; if (up) return 1; if (dn) return -1; return 0; }],
  ["new20_run", "New 20-bar high run", "MOM", (C, i) => { if (C.don20H[i] == null) return 0; if (C.h[i] > C.don20H[i] && C.c[i] > C.o[i]) return 1; if (C.l[i] < C.don20L[i] && C.c[i] < C.o[i]) return -1; return 0; }],
  ["mom_5bar", "5-bar momentum vs ATR", "MOM", (C, i) => { const a = C.atr[i]; if (a == null) return 0; const chg = C.c[i] - C.c[i - 5]; if (chg > 1.5 * a) return 1; if (chg < -1.5 * a) return -1; return 0; }],
];

// ---- build the ATR bracket for an entry signal ----
function brk(price, a, dir, s, t) {
  return dir === 1
    ? { dir: 1, entry: price, stop: price - s * a, target: price + t * a }
    : { dir: -1, entry: price, stop: price + s * a, target: price - t * a };
}
function evalStrategy(bars, C, dirAt, ex) {
  const sig = new Array(bars.length).fill(null);
  for (let i = 210; i < bars.length; i++) {
    const a = C.atr[i]; if (a == null) continue;
    let d = 0; try { d = dirAt(C, i) || 0; } catch { continue; }
    if (d) sig[i] = brk(C.c[i], a, d, ex.s, ex.t);
  }
  const ledger = Lab.runLedger(bars, sig);
  const t = Lab.tally(ledger);
  const net$ = t.netPts * DPP, dd$ = t.ddPts * DPP, wd$ = -t.worstDayPts * DPP;
  return { n: t.n, win: +t.winRate.toFixed(1), pf: t.pf === Infinity ? 99 : +t.pf.toFixed(2), net$: Math.round(net$), dd$: Math.round(dd$), wd$: Math.round(wd$), mls: t.maxLossStreak, feasible: wd$ < DLL && dd$ < MLL };
}
function loadJson(p) { return JSON.parse(fs.readFileSync(p, "utf8")).filter(b => b && isFinite(b.c)).sort((a, b) => a.t - b.t); }
function span(bars) { return [bars[0].t, bars[bars.length - 1].t].map(s => new Date(s * 1000).toISOString().slice(0, 10)); }
const dol = x => (x >= 0 ? "+$" : "-$") + Math.abs(x).toLocaleString();

function main() {
  let bars13 = null; try { bars13 = Lab.loadCsv(Lab.CSV_13); } catch (e) { console.log("13d CSV missing:", e.message); }
  const bars58 = loadJson(path.join(__dirname, "data", "nq-5m.json"));
  const prime = bars13 || bars58, primeName = bars13 ? "13d" : "58d";
  const Cp = buildContext(prime), Ca = buildContext(bars58);
  const span13 = bars13 ? span(bars13) : null, span58 = span(bars58);

  const strategies = [];
  for (const [key, name, cat, fn] of ENTRIES) for (const ex of EXITS) strategies.push({ key: `${key}|${ex.tag}`, name: `${name} · ${ex.tag}`, cat, fn, ex });
  console.log(`Generated ${strategies.length} strategies (${ENTRIES.length} entries x ${EXITS.length} exits).`);

  const results = strategies.map(st => {
    const P = evalStrategy(prime, Cp, st.fn, st.ex);
    const A = evalStrategy(bars58, Ca, st.fn, st.ex);
    // robust score: both samples net-positive + feasible + enough trades, ranked by weakest net
    const robust = P.net$ > 0 && A.net$ > 0 && P.feasible && A.feasible && P.n >= 5 && A.n >= 8;
    const score = robust ? Math.min(P.net$, A.net$) : -1e9 + P.net$ + A.net$;
    return { ...st, P, A, robust, score };
  }).sort((a, b) => b.score - a.score);
  results.forEach((r, i) => r.rank = i + 1);

  const robust = results.filter(r => r.robust);
  // softer tier: net-positive on BOTH samples + feasible on the LARGER 58d sample (the more
  // trustworthy read) + enough trades. These are the real candidates to deepen / size down.
  const promising = results.filter(r => !r.robust && r.P.net$ > 0 && r.A.net$ > 0 && r.A.feasible && r.P.n >= 5 && r.A.n >= 8);
  console.log(`\nRobust survivors (net+ & feasible on BOTH samples, >=5/>=8 trades): ${robust.length} of ${results.length}`);
  console.log(`Promising (net+ both + 58d-feasible): ${promising.length}`);
  console.log("rank  strategy".padEnd(46) + "cat".padEnd(7) + "13dTrd 13dWin 13dPF   13dNet   13dDD  58dNet  58dPF");
  for (const r of results.slice(0, 25)) {
    console.log(String(r.rank).padStart(4) + "  " + r.name.slice(0, 38).padEnd(40) + r.cat.padEnd(7) +
      String(r.P.n).padStart(5) + (r.P.win + "%").padStart(7) + String(r.P.pf).padStart(6) +
      dol(r.P.net$).padStart(9) + ("-$" + r.P.dd$).padStart(8) + dol(r.A.net$).padStart(8) + String(r.A.pf).padStart(6) +
      (r.robust ? "  ✅" : ""));
  }

  // ---- markdown report ----
  const md = [];
  md.push(`# Strategy generator — 150 candidates (${new Date().toISOString().slice(0, 10)})`);
  md.push(`\n**${ENTRIES.length} distinct entry edges × ${EXITS.length} reward:risk exits = ${results.length} strategies.** No time-of-day limit (any RTH bar). Biased toward FVG / sweep / reversal / mean-revert families per the power-hour post-mortem (0-for-11 momentum-chase) and the [WICK] liquidity-sweep example.`);
  md.push(`\nBacktested on **${primeName}** (${(span13 || span58).join(" → ")}) PRIMARY + **58d** (${span58.join(" → ")}) out-of-sample. Dollars @5 MNQ ($10/pt), gross (no slippage/commissions). "Feasible" = worst day < $${DLL} (DLL) and max drawdown < $${MLL} (MLL).`);
  md.push(`\n- **Robust survivors** (net-positive AND feasible on BOTH samples, ≥5/≥8 trades): **${robust.length} of ${results.length}**.`);
  md.push(`\n> SCREEN, not proof. 13 days is tiny; survivors must also clear the 58-day column and ideally fresh out-of-sample before any live use. Exits use a fixed ATR bracket — no per-strategy stop/target tuning beyond the 3 RR profiles.`);
  md.push(`\n## Robust survivors (ranked by weakest-sample net)\n`);
  if (robust.length) {
    md.push(`| # | Strategy | Cat | 13d Trd | 13d Win% | 13d PF | 13d Net | 13d DD | 58d Trd | 58d Net | 58d PF |`);
    md.push(`|---|----------|-----|----:|----:|---:|------:|------:|----:|------:|---:|`);
    for (const r of robust) md.push(`| ${r.rank} | ${r.name} | ${r.cat} | ${r.P.n} | ${r.P.win} | ${r.P.pf} | ${dol(r.P.net$)} | -$${r.P.dd$} | ${r.A.n} | ${dol(r.A.net$)} | ${r.A.pf} |`);
  } else md.push(`_None cleared the strict both-samples-feasible bar — expected on 13 days (its worst-day wall is noisy). See the promising tier below._`);
  md.push(`\n## Promising (net+ on both, feasible on the larger 58d sample) — ${promising.length}\n`);
  md.push(`These bust the Combine drawdown wall at **5 MNQ** on the tiny 13d sample but are net-positive on both and feasible on 58d — i.e. real candidates to deepen and/or trade at smaller size.\n`);
  if (promising.length) {
    md.push(`| # | Strategy | Cat | 13d Trd | 13d Win% | 13d PF | 13d Net | 13d DD | 58d Trd | 58d Net | 58d PF | 58d DD |`);
    md.push(`|---|----------|-----|----:|----:|---:|------:|------:|----:|------:|---:|------:|`);
    for (const r of promising.slice(0, 25)) md.push(`| ${r.rank} | ${r.name} | ${r.cat} | ${r.P.n} | ${r.P.win} | ${r.P.pf} | ${dol(r.P.net$)} | -$${r.P.dd$} | ${r.A.n} | ${dol(r.A.net$)} | ${r.A.pf} | -$${r.A.dd$} |`);
  }
  md.push(`\n## Top 30 by score (all strategies)\n`);
  md.push(`| # | Strategy | Cat | 13d Trd | 13d Win% | 13d PF | 13d Net | 13d DD | 58d Net | 58d PF | Robust |`);
  md.push(`|---|----------|-----|----:|----:|---:|------:|------:|------:|---:|:--:|`);
  for (const r of results.slice(0, 30)) md.push(`| ${r.rank} | ${r.name} | ${r.cat} | ${r.P.n} | ${r.P.win} | ${r.P.pf} | ${dol(r.P.net$)} | -$${r.P.dd$} | ${dol(r.A.net$)} | ${r.A.pf} | ${r.robust ? "✅" : ""} |`);

  fs.mkdirSync(path.dirname(OUT_MD), { recursive: true });
  fs.writeFileSync(OUT_MD, md.join("\n") + "\n");
  fs.writeFileSync(OUT_JSON, JSON.stringify(results.map(r => ({ rank: r.rank, key: r.key, name: r.name, cat: r.cat, robust: r.robust, P: r.P, A: r.A })), null, 2));
  console.log(`\nReport -> ${OUT_MD}`);
  console.log(`JSON   -> ${OUT_JSON}`);
}

module.exports = { ENTRIES, EXITS, buildContext, evalStrategy, brk, DPP, DLL, MLL };
if (require.main === module) main();
