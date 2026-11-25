// =============================================================
//  lab-new4.js — batch 4: 50 BRAND-NEW intraday strategies, tested on BOTH the
//  13-day MNQ CSV and the 58-day Yahoo NQ=F 5m chart, reported at 5 MNQ AND 1 MNQ.
//
//  Goal (user request): research 50 new strategies, run them on the 13d + 58d
//  graphs at 5 MNQ ($10/pt) and 1 MNQ ($2/pt), send the results.
//
//  Fair exit model (identical to batches 1-3): RTH entries 09:30-16:00 ET,
//  flat by 16:00 ET, one position at a time, stop-first on ties, mark-to-close
//  at session end. Raw-edge runner (no eval lockout) so we see the true edge;
//  TopStep $50K Combine survival is FLAGGED per size (DLL $1,000 worst-day,
//  MLL $2,000 max drawdown) but not enforced.
//
//  50 distinct triggers, none a duplicate of batch 1/2/3. Spread across
//  mean-reversion, momentum, breakout, candle/pattern, time-of-day, and
//  volatility archetypes so the leaderboard samples a wide idea space.
//
//  Small sample warning: 13 days is a single-regime fingerprint; the 58-day
//  run is the real out-of-sample test. Treat 13d as an idea screen, 58d as
//  the verdict. Neither is multi-year proof.
//
//  DATA-ONLY / TopStep-compliant: reads a local CSV + public Yahoo feed,
//  never places an order.
//  Run:  node lab-new4.js
// =============================================================
"use strict";

const fs = require("fs");
const Yahoo = require("./yahoo.js");
require("./public/indicators.js");
const I = globalThis.Indicators;

const CSV_13 = "C:\\Users\\kaide\\Downloads\\CME_MINI_DL_MNQ1!, 5.csv";
const DLL = 1000, MLL = 2000;            // $50K Combine limits (dollars)
const f = (x, d = 0) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));

// ---------------- bar IO + ET helpers ----------------
function loadCsv(p) {
  const rows = fs.readFileSync(p, "utf8").trim().split(/\r?\n/);
  const out = [];
  for (let i = 1; i < rows.length; i++) { const c = rows[i].split(","); const t = +c[0]; if (!t) continue; out.push({ t, o: +c[1], h: +c[2], l: +c[3], c: +c[4], v: +(c[5] || 0) }); }
  out.sort((a, b) => a.t - b.t); return out;
}
function etParts(s) {
  const e = new Date(new Date(s * 1000).toLocaleString("en-US", { timeZone: "America/New_York" }));
  return { day: e.getDay(), mins: e.getHours() * 60 + e.getMinutes(), k: `${e.getFullYear()}-${e.getMonth()}-${e.getDate()}` };
}
const dayKeyOf = (s) => etParts(s).k;
const RTH_START = 570, RTH_END = 960;
function isInRTH(s) { const p = etParts(s); return p.day !== 0 && p.day !== 6 && p.mins >= RTH_START && p.mins < RTH_END; }

// ---------------- exit sim + runner + tally ----------------
function simulateTrade(bars, entryIdx, sig) {
  const isLong = sig.dir === 1, entry = sig.entry, startDay = dayKeyOf(bars[entryIdx].t);
  for (let k = entryIdx + 1; k < bars.length; k++) {
    if (dayKeyOf(bars[k].t) !== startDay || !isInRTH(bars[k].t)) { const px = bars[k - 1].c; return { pts: isLong ? px - entry : entry - px, exitIdx: k - 1 }; }
    const b = bars[k];
    if (isLong ? b.l <= sig.stop : b.h >= sig.stop) return { pts: isLong ? sig.stop - entry : entry - sig.stop, exitIdx: k };
    if (isLong ? b.h >= sig.target : b.l <= sig.target) return { pts: isLong ? sig.target - entry : entry - sig.target, exitIdx: k };
  }
  const px = bars[bars.length - 1].c; return { pts: isLong ? px - entry : entry - px, exitIdx: bars.length - 1 };
}
function runSignals(bars, sig) {
  const trades = []; let i = 1;
  while (i < bars.length) {
    if (sig[i] && isInRTH(bars[i].t)) { const r = simulateTrade(bars, i, sig[i]); trades.push({ date: dayKeyOf(bars[i].t), pts: r.pts }); i = r.exitIdx + 1; }
    else i++;
  }
  return tally(trades);
}
// Same walk as runSignals, but returns the per-trade ledger (with timestamps)
// instead of just the tally — used for equity-curve / drawdown forensics.
function runLedger(bars, sig) {
  const trades = []; let i = 1;
  while (i < bars.length) {
    if (sig[i] && isInRTH(bars[i].t)) {
      const r = simulateTrade(bars, i, sig[i]);
      trades.push({ date: dayKeyOf(bars[i].t), pts: r.pts, entryT: bars[i].t, exitT: bars[r.exitIdx].t, dir: sig[i].dir });
      i = r.exitIdx + 1;
    } else i++;
  }
  return trades;
}
function tally(trades) {
  const wins = trades.filter((t) => t.pts > 0);
  const gW = wins.reduce((s, t) => s + t.pts, 0);
  const gL = Math.abs(trades.filter((t) => t.pts <= 0).reduce((s, t) => s + t.pts, 0));
  const netPts = trades.reduce((s, t) => s + t.pts, 0);
  let peak = 0, cum = 0, maxDD = 0;
  for (const t of trades) { cum += t.pts; peak = Math.max(peak, cum); maxDD = Math.max(maxDD, peak - cum); }
  let streak = 0, maxLossStreak = 0;
  for (const t of trades) { if (t.pts <= 0) { streak++; maxLossStreak = Math.max(maxLossStreak, streak); } else streak = 0; }
  const byDay = new Map();
  for (const t of trades) byDay.set(t.date, (byDay.get(t.date) || 0) + t.pts);
  const worstDayPts = trades.length ? Math.min(0, ...byDay.values()) : 0;
  return { n: trades.length, winRate: trades.length ? (wins.length / trades.length) * 100 : 0, pf: gL > 0 ? gW / gL : (gW > 0 ? Infinity : 0), netPts, ddPts: maxDD, worstDayPts, maxLossStreak };
}
const long = (e, stop, target) => (target > e && stop < e) ? { dir: 1, entry: e, stop, target } : null;
const short = (e, stop, target) => (target < e && stop > e) ? { dir: -1, entry: e, stop, target } : null;

// ---------------- precompute helpers ----------------
function rollExtremesPrior(arr, n) {
  const hi = new Array(arr.length).fill(null), lo = new Array(arr.length).fill(null);
  for (let i = n; i < arr.length; i++) { let mx = -Infinity, mn = Infinity; for (let k = i - n; k < i; k++) { mx = Math.max(mx, arr[k]); mn = Math.min(mn, arr[k]); } hi[i] = mx; lo[i] = mn; }
  return { hi, lo };
}
function dayOpenArr(bars) {
  const m = new Map();
  for (const b of bars) { if (!isInRTH(b.t)) continue; const k = dayKeyOf(b.t); if (!m.has(k)) m.set(k, b.o); }
  return bars.map((b) => (m.has(dayKeyOf(b.t)) ? m.get(dayKeyOf(b.t)) : null));
}
function priorRthHLC(bars) {
  const order = [], hi = new Map(), lo = new Map(), cl = new Map();
  for (const b of bars) { if (!isInRTH(b.t)) continue; const k = dayKeyOf(b.t); if (!hi.has(k)) { order.push(k); hi.set(k, b.h); lo.set(k, b.l); } hi.set(k, Math.max(hi.get(k), b.h)); lo.set(k, Math.min(lo.get(k), b.l)); cl.set(k, b.c); }
  const prior = new Map();
  for (let d = 1; d < order.length; d++) prior.set(order[d], { h: hi.get(order[d - 1]), l: lo.get(order[d - 1]), c: cl.get(order[d - 1]) });
  return prior;
}
function rangeWindow(bars, startMin, endMin) { // dayKey -> {h,l} over [startMin,endMin) ET
  const hi = new Map(), lo = new Map();
  for (const b of bars) { const p = etParts(b.t); if (p.day === 0 || p.day === 6) continue; if (p.mins >= startMin && p.mins < endMin) { const k = p.k; if (!hi.has(k)) { hi.set(k, b.h); lo.set(k, b.l); } hi.set(k, Math.max(hi.get(k), b.h)); lo.set(k, Math.min(lo.get(k), b.l)); } }
  return { hi, lo };
}
function sessionVWAPbands(bars) {
  const vwap = new Array(bars.length).fill(null), sd = new Array(bars.length).fill(null);
  let curDay = null, vNum = 0, vDen = 0, vNum2 = 0;
  for (let i = 0; i < bars.length; i++) {
    const p = etParts(bars[i].t);
    if (p.k !== curDay) { curDay = p.k; vNum = 0; vDen = 0; vNum2 = 0; }
    if (p.mins >= RTH_START && p.mins < RTH_END) { const hlc3 = (bars[i].h + bars[i].l + bars[i].c) / 3, v = bars[i].v || 1; vNum += hlc3 * v; vNum2 += hlc3 * hlc3 * v; vDen += v; }
    if (vDen > 0) { const m = vNum / vDen; vwap[i] = m; sd[i] = Math.sqrt(Math.max(0, vNum2 / vDen - m * m)); }
  }
  return { vwap, sd };
}
function cci(high, low, close, n) {
  const tp = high.map((h, i) => (h + low[i] + close[i]) / 3), ma = I.sma(tp, n), out = new Array(close.length).fill(null);
  for (let i = n - 1; i < close.length; i++) { let md = 0; for (let k = i - n + 1; k <= i; k++) md += Math.abs(tp[k] - ma[i]); md /= n; out[i] = md === 0 ? 0 : (tp[i] - ma[i]) / (0.015 * md); }
  return out;
}
function williamsR(high, low, close, n) {
  const out = new Array(close.length).fill(null);
  for (let i = n - 1; i < close.length; i++) { let hh = -Infinity, ll = Infinity; for (let k = i - n + 1; k <= i; k++) { hh = Math.max(hh, high[k]); ll = Math.min(ll, low[k]); } out[i] = hh > ll ? -100 * (hh - close[i]) / (hh - ll) : -50; }
  return out;
}
function heikin(bars) {
  const haC = new Array(bars.length), haO = new Array(bars.length);
  for (let i = 0; i < bars.length; i++) { haC[i] = (bars[i].o + bars[i].h + bars[i].l + bars[i].c) / 4; haO[i] = i === 0 ? (bars[i].o + bars[i].c) / 2 : (haO[i - 1] + haC[i - 1]) / 2; }
  return { haC, haO };
}
function stochKD(high, low, close, n) {
  const K = new Array(close.length).fill(null);
  for (let i = n - 1; i < close.length; i++) { let hh = -Infinity, ll = Infinity; for (let k = i - n + 1; k <= i; k++) { hh = Math.max(hh, high[k]); ll = Math.min(ll, low[k]); } K[i] = hh > ll ? (close[i] - ll) / (hh - ll) * 100 : 50; }
  const D = I.sma(K.map((v) => v == null ? 0 : v), 3).map((v, i) => K[i] == null ? null : v);
  return { K, D };
}
function roc(close, n) { return close.map((c, i) => (i < n || close[i - n] === 0) ? null : (c - close[i - n]) / close[i - n] * 100); }
function lastSwing(arr, isHigh, left, right) {
  const n = arr.length, out = new Array(n).fill(null); let last = null;
  for (let i = 0; i < n; i++) { const c = i - right; if (c >= left) { let piv = true; for (let k = 1; k <= left && piv; k++) if (isHigh ? arr[c - k] > arr[c] : arr[c - k] < arr[c]) piv = false; for (let k = 1; k <= right && piv; k++) if (isHigh ? arr[c + k] > arr[c] : arr[c + k] < arr[c]) piv = false; if (piv) last = arr[c]; } out[i] = last; }
  return out;
}
const firstRthBar = (bars, i, dk) => { const p = etParts(bars[i].t); return p.mins >= RTH_START && p.mins < RTH_START + 5 && (!isInRTH(bars[i - 1].t) || dayKeyOf(bars[i - 1].t) !== dk); };

// ============================ 50 NEW STRATEGIES ============================
const KEYS = [
  // mean-reversion (1-10)
  "rsi2Ext", "bbLowerTag", "cciRev", "willRev", "vwap3sig", "doubleDown", "zscoreRev", "rsiDiv", "keltFade", "gapFill",
  // momentum (11-20)
  "macdZero", "diRising", "rsi50", "threeBarMom", "volThrust", "consec4", "emaSlope", "newHigh20", "squeezeRel", "haStrong",
  // breakout (21-30)
  "orbHour", "don10", "don55", "priorDayBrk", "nr4Break", "rangeComp", "vwapBandBrk", "pivotR2S2", "halfGapBrk", "downbarBrk",
  // pattern (31-40)
  "bullFlag", "pinBar", "engulf", "dblBottom", "insideStack", "threeSoldiers", "morningRev", "hammerReclaim", "fakeout", "nr7Break",
  // time/session (41-45)
  "lunchBrk", "powerHour", "firstHrFade", "middayMR", "openDrive",
  // volatility/other (46-50)
  "atrExpBrk", "stdevSpike", "macdHistTurn", "rsiBandRide", "diCross",
];
const NAMES = {
  rsi2Ext: "1. RSI(2) extreme fade", bbLowerTag: "2. BB lower-tag reclaim", cciRev: "3. CCI(20) reversion", willRev: "4. Williams%R reversal",
  vwap3sig: "5. VWAP 3-sigma fade", doubleDown: "6. Two-down-close bounce", zscoreRev: "7. Z-score(2.5) fade", rsiDiv: "8. RSI divergence (lite)",
  keltFade: "9. Keltner band fade", gapFill: "10. Opening gap-fill",
  macdZero: "11. MACD zero-line cross", diRising: "12. ADX rising + DI dir", rsi50: "13. RSI(14) 50-cross trend", threeBarMom: "14. 3-bar HH momentum",
  volThrust: "15. Volume thrust (2x)", consec4: "16. 4 consecutive closes", emaSlope: "17. Steep EMA21 slope", newHigh20: "18. New 20-bar high run",
  squeezeRel: "19. BB/Keltner squeeze release", haStrong: "20. Heikin strong-body trend",
  orbHour: "21. Opening-hour range break", don10: "22. Donchian-10 break", don55: "23. Donchian-55 break", priorDayBrk: "24. Prior-day H/L break",
  nr4Break: "25. NR4 narrow-range break", rangeComp: "26. Range-compression break", vwapBandBrk: "27. VWAP +1sig band break", pivotR2S2: "28. Pivot R2/S2 break",
  halfGapBrk: "29. Opening 15m range break", downbarBrk: "30. Down-bar cluster break",
  bullFlag: "31. Bull/bear flag break", pinBar: "32. Pin-bar rejection", engulf: "33. Engulfing in trend", dblBottom: "34. Double-bottom/top neckline",
  insideStack: "35. Two-inside-bar break", threeSoldiers: "36. Three soldiers/crows", morningRev: "37. Morning reversal", hammerReclaim: "38. Hammer SMA20 reclaim",
  fakeout: "39. Failed-breakout fade", nr7Break: "40. NR7 narrow-range break",
  lunchBrk: "41. Lunch-range afternoon brk", powerHour: "42. Power-hour momentum", firstHrFade: "43. First-hour extreme fade", middayMR: "44. Midday BB mean-rev", openDrive: "45. Open-drive continuation",
  atrExpBrk: "46. ATR-expansion break", stdevSpike: "47. Stdev-spike momentum", macdHistTurn: "48. MACD-hist early turn", rsiBandRide: "49. RSI band-ride dip buy", diCross: "50. +DI/-DI cross + ADX",
};

function buildAll(bars) {
  const close = bars.map((b) => b.c), high = bars.map((b) => b.h), low = bars.map((b) => b.l), open = bars.map((b) => b.o), vol = bars.map((b) => b.v);
  const N = bars.length;
  const atr = I.atr(high, low, close, 14), atr5 = I.atr(high, low, close, 5), atr20 = I.atr(high, low, close, 20);
  const ema200 = I.ema(close, 200), ema21 = I.ema(close, 21), ema20 = I.ema(close, 20), ema8 = I.ema(close, 8);
  const sma20 = I.sma(close, 20), dev = I.stdev(close, 20);
  const upBB = sma20.map((v, k) => v == null ? null : v + 2 * dev[k]), loBB = sma20.map((v, k) => v == null ? null : v - 2 * dev[k]);
  const rsi2 = I.rsi(close, 2), rsi14 = I.rsi(close, 14);
  const { macdLine, signalLine } = I.macd(close, 12, 26, 9);
  const hist = macdLine.map((v, k) => (v == null || signalLine[k] == null) ? null : v - signalLine[k]);
  const dmiRaw = I.dmi(high, low, close, 14, 14);
  const plusDI = dmiRaw.plusDI || dmiRaw.diPlus || dmiRaw.plus || dmiRaw.pdi;
  const minusDI = dmiRaw.minusDI || dmiRaw.diMinus || dmiRaw.minus || dmiRaw.mdi;
  const adx = dmiRaw.adx || dmiRaw.adxV || dmiRaw.ADX;
  const { vwap, sd } = sessionVWAPbands(bars);
  const cciA = cci(high, low, close, 20), wprA = williamsR(high, low, close, 14);
  const { haC, haO } = heikin(bars);
  const dOpen = dayOpenArr(bars), pHLC = priorRthHLC(bars);
  const d10 = rollExtremesPrior(high, 10), d10L = rollExtremesPrior(low, 10);
  const d20 = rollExtremesPrior(high, 20), d20L = rollExtremesPrior(low, 20);
  const d55 = rollExtremesPrior(high, 55), d55L = rollExtremesPrior(low, 55);
  const volAvg = I.sma(vol, 20);
  const orbH = rangeWindow(bars, 570, 630);   // 09:30-10:30
  const or15 = rangeWindow(bars, 570, 585);   // 09:30-09:45
  const lunch = rangeWindow(bars, 720, 780);  // 12:00-13:00
  const fhr = rangeWindow(bars, 570, 630);    // first hour for fade
  const keltUp = ema20.map((v, k) => v == null || atr20[k] == null ? null : v + 1.5 * atr20[k]);
  const keltLo = ema20.map((v, k) => v == null || atr20[k] == null ? null : v - 1.5 * atr20[k]);
  const zeros = macdLine.map(() => 0);
  const xMacd0 = I.crossover(macdLine, zeros), xMacd0D = I.crossunder(macdLine, zeros);

  const mk = () => new Array(N).fill(null);
  const S = {}; for (const k of KEYS) S[k] = mk();
  const fired = {}; for (const k of ["orbHour", "halfGapBrk", "gapFill", "morningRev"]) fired[k] = new Set();

  for (let i = 8; i < N; i++) {
    const e = close[i], a = atr[i];
    if (a == null) continue;
    const p = etParts(bars[i].t), dk = p.k, ph = pHLC.get(dk);
    const up200 = ema200[i] != null && e > ema200[i], dn200 = ema200[i] != null && e < ema200[i];

    // ---------- MEAN-REVERSION ----------
    // 1) RSI(2) extreme: <5 long / >95 short, target SMA20, stop 1.5ATR
    if (rsi2[i] != null && sma20[i] != null) {
      if (rsi2[i] < 5 && e < sma20[i]) S.rsi2Ext[i] = long(e, e - 1.5 * a, sma20[i]);
      else if (rsi2[i] > 95 && e > sma20[i]) S.rsi2Ext[i] = short(e, e + 1.5 * a, sma20[i]);
    }
    // 2) BB lower-tag reclaim: prior bar tagged band, this bar closes back inside; fade to basis
    if (loBB[i] != null && loBB[i - 1] != null) {
      if (low[i - 1] <= loBB[i - 1] && e > loBB[i] && close[i] > open[i]) S.bbLowerTag[i] = long(e, low[i - 1], sma20[i]);
      else if (high[i - 1] >= upBB[i - 1] && e < upBB[i] && close[i] < open[i]) S.bbLowerTag[i] = short(e, high[i - 1], sma20[i]);
    }
    // 3) CCI(20) reversion: cross back from <-150 / >150, target SMA20
    if (cciA[i] != null && cciA[i - 1] != null && sma20[i] != null) {
      if (cciA[i - 1] < -150 && cciA[i] > -150) S.cciRev[i] = long(e, e - 1.5 * a, sma20[i] > e ? sma20[i] : e + a);
      else if (cciA[i - 1] > 150 && cciA[i] < 150) S.cciRev[i] = short(e, e + 1.5 * a, sma20[i] < e ? sma20[i] : e - a);
    }
    // 4) Williams %R reversal: from <-90 rising / >-10 falling
    if (wprA[i] != null && wprA[i - 1] != null) {
      if (wprA[i - 1] < -90 && wprA[i] > -90) S.willRev[i] = long(e, e - 1.5 * a, e + 1.5 * a);
      else if (wprA[i - 1] > -10 && wprA[i] < -10) S.willRev[i] = short(e, e + 1.5 * a, e - 1.5 * a);
    }
    // 5) VWAP 3-sigma fade back to VWAP
    if (vwap[i] != null && sd[i] > 0) {
      const z = (e - vwap[i]) / sd[i];
      if (z >= 3 && close[i] < open[i]) S.vwap3sig[i] = short(e, e + 1.2 * a, vwap[i]);
      else if (z <= -3 && close[i] > open[i]) S.vwap3sig[i] = long(e, e - 1.2 * a, vwap[i]);
    }
    // 6) Two-down-close below SMA20 then up-close bounce
    if (sma20[i] != null && close[i - 1] < close[i - 2] && close[i - 2] < close[i - 3] && close[i - 1] < sma20[i] && close[i] > close[i - 1]) S.doubleDown[i] = long(e, low[i - 1], sma20[i] > e ? sma20[i] : e + 1.5 * a);
    else if (sma20[i] != null && close[i - 1] > close[i - 2] && close[i - 2] > close[i - 3] && close[i - 1] > sma20[i] && close[i] < close[i - 1]) S.doubleDown[i] = short(e, high[i - 1], sma20[i] < e ? sma20[i] : e - 1.5 * a);
    // 7) Z-score fade: |z|>2.5 vs SMA20/stdev, target SMA20
    if (sma20[i] != null && dev[i] > 0) {
      const z = (e - sma20[i]) / dev[i];
      if (z > 2.5) S.zscoreRev[i] = short(e, e + 1.2 * a, sma20[i]);
      else if (z < -2.5) S.zscoreRev[i] = long(e, e - 1.2 * a, sma20[i]);
    }
    // 8) RSI divergence (lite): price new 10-bar low but RSI14 higher than 10 bars ago -> long
    if (rsi14[i] != null && rsi14[i - 10] != null) {
      let nl = true, nh = true; for (let k = 1; k <= 10; k++) { if (low[i] >= low[i - k]) nl = false; if (high[i] <= high[i - k]) nh = false; }
      if (nl && rsi14[i] > rsi14[i - 10] && close[i] > open[i]) S.rsiDiv[i] = long(e, low[i] - 0.2 * a, e + 2 * a);
      else if (nh && rsi14[i] < rsi14[i - 10] && close[i] < open[i]) S.rsiDiv[i] = short(e, high[i] + 0.2 * a, e - 2 * a);
    }
    // 9) Keltner band fade back to EMA20
    if (keltUp[i] != null) {
      if (high[i] >= keltUp[i] && e < keltUp[i] && close[i] < open[i]) S.keltFade[i] = short(e, high[i] + 0.3 * a, ema20[i]);
      else if (low[i] <= keltLo[i] && e > keltLo[i] && close[i] > open[i]) S.keltFade[i] = long(e, low[i] - 0.3 * a, ema20[i]);
    }
    // 10) Opening gap-fill: first RTH bar gaps vs prior close, fade toward prior close
    if (firstRthBar(bars, i, dk) && ph && !fired.gapFill.has(dk)) {
      const gap = open[i] - ph.c;
      if (gap > 0.5 * a && gap < 4 * a) { fired.gapFill.add(dk); S.gapFill[i] = short(e, e + 1.2 * a, ph.c); }
      else if (gap < -0.5 * a && gap > -4 * a) { fired.gapFill.add(dk); S.gapFill[i] = long(e, e - 1.2 * a, ph.c); }
    }

    // ---------- MOMENTUM ----------
    // 11) MACD zero-line cross with trend
    if (up200 && xMacd0[i]) S.macdZero[i] = long(e, e - 1.5 * a, e + 2 * a);
    else if (dn200 && xMacd0D[i]) S.macdZero[i] = short(e, e + 1.5 * a, e - 2 * a);
    // 12) ADX rising >20 + DI direction
    if (adx && adx[i] != null && adx[i - 1] != null && adx[i] > 20 && adx[i] > adx[i - 1] && plusDI && plusDI[i] != null) {
      if (plusDI[i] > minusDI[i] && up200) S.diRising[i] = long(e, e - 1.5 * a, e + 2.5 * a);
      else if (minusDI[i] > plusDI[i] && dn200) S.diRising[i] = short(e, e + 1.5 * a, e - 2.5 * a);
    }
    // 13) RSI(14) crosses 50 with trend
    if (rsi14[i] != null && rsi14[i - 1] != null) {
      if (up200 && rsi14[i - 1] <= 50 && rsi14[i] > 50) S.rsi50[i] = long(e, e - 1.5 * a, e + 2 * a);
      else if (dn200 && rsi14[i - 1] >= 50 && rsi14[i] < 50) S.rsi50[i] = short(e, e + 1.5 * a, e - 2 * a);
    }
    // 14) 3-bar higher-high momentum continuation
    if (high[i] > high[i - 1] && high[i - 1] > high[i - 2] && close[i] > close[i - 1] && close[i - 1] > close[i - 2]) S.threeBarMom[i] = long(e, low[i - 2], e + 1.5 * (e - low[i - 2]));
    else if (low[i] < low[i - 1] && low[i - 1] < low[i - 2] && close[i] < close[i - 1] && close[i - 1] < close[i - 2]) S.threeBarMom[i] = short(e, high[i - 2], e - 1.5 * (high[i - 2] - e));
    // 15) Volume thrust: vol>2x avg + decisive close direction
    if (volAvg[i] > 0 && vol[i] > 2 * volAvg[i]) {
      const rng = high[i] - low[i];
      if (rng > 0 && close[i] >= high[i] - 0.25 * rng) S.volThrust[i] = long(e, low[i], e + 2 * a);
      else if (rng > 0 && close[i] <= low[i] + 0.25 * rng) S.volThrust[i] = short(e, high[i], e - 2 * a);
    }
    // 16) 4 consecutive closes same direction (momentum burst)
    if (close[i] > close[i - 1] && close[i - 1] > close[i - 2] && close[i - 2] > close[i - 3] && close[i - 3] > close[i - 4]) S.consec4[i] = long(e, e - 1.5 * a, e + 2 * a);
    else if (close[i] < close[i - 1] && close[i - 1] < close[i - 2] && close[i - 2] < close[i - 3] && close[i - 3] < close[i - 4]) S.consec4[i] = short(e, e + 1.5 * a, e - 2 * a);
    // 17) Steep EMA21 slope (> 0.15 ATR/bar) enter with trend
    if (ema21[i] != null && ema21[i - 3] != null) {
      const slope = (ema21[i] - ema21[i - 3]) / 3;
      if (up200 && slope > 0.15 * a && close[i] > open[i]) S.emaSlope[i] = long(e, e - 1.5 * a, e + 2 * a);
      else if (dn200 && slope < -0.15 * a && close[i] < open[i]) S.emaSlope[i] = short(e, e + 1.5 * a, e - 2 * a);
    }
    // 18) New 20-bar high close -> momentum continuation
    if (d20.hi[i] != null) {
      if (e > d20.hi[i] && close[i] > open[i]) S.newHigh20[i] = long(e, e - 1.5 * a, e + 2.5 * a);
      else if (e < d20L.lo[i] && close[i] < open[i]) S.newHigh20[i] = short(e, e + 1.5 * a, e - 2.5 * a);
    }
    // 19) Squeeze release: BB inside Keltner last bar, expansion bar this bar
    if (upBB[i - 1] != null && keltUp[i - 1] != null) {
      const squeezed = upBB[i - 1] < keltUp[i - 1] && loBB[i - 1] > keltLo[i - 1];
      if (squeezed) {
        if (close[i] > open[i] && e > upBB[i]) S.squeezeRel[i] = long(e, e - 1.5 * a, e + 2.5 * a);
        else if (close[i] < open[i] && e < loBB[i]) S.squeezeRel[i] = short(e, e + 1.5 * a, e - 2.5 * a);
      }
    }
    // 20) Heikin-Ashi strong body (flat-bottom up / flat-top down) with trend
    {
      const body = Math.abs(haC[i] - haO[i]), rng = high[i] - low[i];
      if (up200 && haC[i] > haO[i] && haC[i - 1] > haO[i - 1] && rng > 0 && body > 0.6 * rng && Math.abs(haO[i] - low[i]) < 0.1 * rng) S.haStrong[i] = long(e, e - 1.5 * a, e + 2 * a);
      else if (dn200 && haC[i] < haO[i] && haC[i - 1] < haO[i - 1] && rng > 0 && body > 0.6 * rng && Math.abs(haO[i] - high[i]) < 0.1 * rng) S.haStrong[i] = short(e, e + 1.5 * a, e - 2 * a);
    }

    // ---------- BREAKOUT ----------
    // 21) Opening-hour (09:30-10:30) range break, once/day after 10:30
    if (p.mins >= 630 && orbH.hi.has(dk) && !fired.orbHour.has(dk)) {
      const rh = orbH.hi.get(dk), rl = orbH.lo.get(dk);
      if (e > rh) { fired.orbHour.add(dk); S.orbHour[i] = long(e, rl, e + 1 * (rh - rl)); }
      else if (e < rl) { fired.orbHour.add(dk); S.orbHour[i] = short(e, rh, e - 1 * (rh - rl)); }
    }
    // 22) Donchian-10 break
    if (d10.hi[i] != null) {
      if (close[i - 1] <= d10.hi[i] && e > d10.hi[i]) S.don10[i] = long(e, e - 1.5 * a, e + 2 * a);
      else if (close[i - 1] >= d10L.lo[i] && e < d10L.lo[i]) S.don10[i] = short(e, e + 1.5 * a, e - 2 * a);
    }
    // 23) Donchian-55 break
    if (d55.hi[i] != null) {
      if (close[i - 1] <= d55.hi[i] && e > d55.hi[i]) S.don55[i] = long(e, e - 2 * a, e + 3 * a);
      else if (close[i - 1] >= d55L.lo[i] && e < d55L.lo[i]) S.don55[i] = short(e, e + 2 * a, e - 3 * a);
    }
    // 24) Prior-day RTH high/low break
    if (ph) {
      if (close[i - 1] <= ph.h && e > ph.h) S.priorDayBrk[i] = long(e, e - 1.5 * a, e + 2.5 * a);
      else if (close[i - 1] >= ph.l && e < ph.l) S.priorDayBrk[i] = short(e, e + 1.5 * a, e - 2.5 * a);
    }
    // 25) NR4 (narrowest range of last 4) then breakout of that bar
    {
      const r0 = high[i - 1] - low[i - 1]; let isNR4 = true;
      for (let k = 2; k <= 4; k++) if (high[i - k] - low[i - k] <= r0) isNR4 = false;
      if (isNR4) { if (e > high[i - 1]) S.nr4Break[i] = long(e, low[i - 1], e + 2 * (high[i - 1] - low[i - 1])); else if (e < low[i - 1]) S.nr4Break[i] = short(e, high[i - 1], e - 2 * (high[i - 1] - low[i - 1])); }
    }
    // 26) Range compression: ATR5 < 0.6 ATR20 then break 10-bar extreme
    if (atr5[i] != null && atr20[i] != null && atr5[i] < 0.6 * atr20[i] && d10.hi[i] != null) {
      if (e > d10.hi[i]) S.rangeComp[i] = long(e, e - 1.2 * a, e + 2.5 * a);
      else if (e < d10L.lo[i]) S.rangeComp[i] = short(e, e + 1.2 * a, e - 2.5 * a);
    }
    // 27) VWAP +1sigma band break momentum
    if (vwap[i] != null && sd[i] > 0) {
      const u1 = vwap[i] + sd[i], l1 = vwap[i] - sd[i];
      if (close[i - 1] <= u1 && e > u1 && up200) S.vwapBandBrk[i] = long(e, vwap[i], e + 2 * a);
      else if (close[i - 1] >= l1 && e < l1 && dn200) S.vwapBandBrk[i] = short(e, vwap[i], e - 2 * a);
    }
    // 28) Pivot R2/S2 break
    if (ph) {
      const P = (ph.h + ph.l + ph.c) / 3, R2 = P + (ph.h - ph.l), S2 = P - (ph.h - ph.l);
      if (close[i - 1] <= R2 && e > R2) S.pivotR2S2[i] = long(e, e - 1.5 * a, e + 2 * a);
      else if (close[i - 1] >= S2 && e < S2) S.pivotR2S2[i] = short(e, e + 1.5 * a, e - 2 * a);
    }
    // 29) Opening 15-min (09:30-09:45) range break, once/day
    if (p.mins >= 585 && or15.hi.has(dk) && !fired.halfGapBrk.has(dk)) {
      const rh = or15.hi.get(dk), rl = or15.lo.get(dk);
      if (e > rh) { fired.halfGapBrk.add(dk); S.halfGapBrk[i] = long(e, rl, e + 1.5 * (rh - rl)); }
      else if (e < rl) { fired.halfGapBrk.add(dk); S.halfGapBrk[i] = short(e, rh, e - 1.5 * (rh - rl)); }
    }
    // 30) Down-bar cluster break: 3 red bars then a green bar breaks the cluster high
    if (close[i - 1] < open[i - 1] && close[i - 2] < open[i - 2] && close[i - 3] < open[i - 3] && close[i] > open[i] && e > Math.max(high[i - 1], high[i - 2], high[i - 3])) S.downbarBrk[i] = long(e, Math.min(low[i - 1], low[i - 2], low[i - 3]), e + 2 * a);
    else if (close[i - 1] > open[i - 1] && close[i - 2] > open[i - 2] && close[i - 3] > open[i - 3] && close[i] < open[i] && e < Math.min(low[i - 1], low[i - 2], low[i - 3])) S.downbarBrk[i] = short(e, Math.max(high[i - 1], high[i - 2], high[i - 3]), e - 2 * a);

    // ---------- PATTERN ----------
    // 31) Bull/bear flag: strong pole (>=2ATR over 3 bars) + 3 tight bars + break
    {
      const pole = close[i - 4] - close[i - 7];
      const flatHi = Math.max(high[i - 1], high[i - 2], high[i - 3]), flatLo = Math.min(low[i - 1], low[i - 2], low[i - 3]);
      const tight = (flatHi - flatLo) < 1.2 * a;
      if (pole > 2 * a && tight && e > flatHi) S.bullFlag[i] = long(e, flatLo, e + Math.abs(pole));
      else if (pole < -2 * a && tight && e < flatLo) S.bullFlag[i] = short(e, flatHi, e - Math.abs(pole));
    }
    // 32) Pin-bar rejection at trend support/resistance
    {
      const body = Math.abs(close[i] - open[i]), upWick = high[i] - Math.max(close[i], open[i]), loWick = Math.min(close[i], open[i]) - low[i];
      if (up200 && loWick > 2 * body && loWick > 0.5 * a && close[i] > open[i]) S.pinBar[i] = long(e, low[i] - 0.2 * a, e + 2 * a);
      else if (dn200 && upWick > 2 * body && upWick > 0.5 * a && close[i] < open[i]) S.pinBar[i] = short(e, high[i] + 0.2 * a, e - 2 * a);
    }
    // 33) Engulfing in trend
    if (up200 && close[i] > open[i] && close[i - 1] < open[i - 1] && close[i] > open[i - 1] && open[i] < close[i - 1]) S.engulf[i] = long(e, low[i], e + 1.5 * (e - low[i]));
    else if (dn200 && close[i] < open[i] && close[i - 1] > open[i - 1] && close[i] < open[i - 1] && open[i] > close[i - 1]) S.engulf[i] = short(e, high[i], e - 1.5 * (high[i] - e));
    // 34) Double-bottom/top: two similar lows within 0.5ATR over last 6 bars, break interim high
    {
      const lo1 = low[i - 5], lo2 = Math.min(low[i - 1], low[i - 2]);
      const interimHi = Math.max(high[i - 1], high[i - 2], high[i - 3], high[i - 4]);
      if (Math.abs(lo1 - lo2) < 0.5 * a && e > interimHi && close[i] > open[i]) S.dblBottom[i] = long(e, Math.min(lo1, lo2), e + 2 * a);
      const hi1 = high[i - 5], hi2 = Math.max(high[i - 1], high[i - 2]);
      const interimLo = Math.min(low[i - 1], low[i - 2], low[i - 3], low[i - 4]);
      if (Math.abs(hi1 - hi2) < 0.5 * a && e < interimLo && close[i] < open[i]) S.dblBottom[i] = short(e, Math.max(hi1, hi2), e - 2 * a);
    }
    // 35) Two inside bars then break
    {
      const inside1 = high[i - 1] <= high[i - 2] && low[i - 1] >= low[i - 2];
      const inside2 = high[i - 2] <= high[i - 3] && low[i - 2] >= low[i - 3];
      if (inside1 && inside2) { if (e > high[i - 1]) S.insideStack[i] = long(e, low[i - 1], e + 2 * (high[i - 1] - low[i - 1])); else if (e < low[i - 1]) S.insideStack[i] = short(e, high[i - 1], e - 2 * (high[i - 1] - low[i - 1])); }
    }
    // 36) Three white soldiers / black crows
    if (close[i] > open[i] && close[i - 1] > open[i - 1] && close[i - 2] > open[i - 2] && close[i] > close[i - 1] && close[i - 1] > close[i - 2]) S.threeSoldiers[i] = long(e, low[i - 2], e + 1.5 * a);
    else if (close[i] < open[i] && close[i - 1] < open[i - 1] && close[i - 2] < open[i - 2] && close[i] < close[i - 1] && close[i - 1] < close[i - 2]) S.threeSoldiers[i] = short(e, high[i - 2], e - 1.5 * a);
    // 37) Morning reversal: by ~10:15, price was >=1ATR below open then reclaims open
    if (p.mins >= 585 && p.mins <= 615 && dOpen[i] != null && !fired.morningRev.has(dk)) {
      const lowestSoFar = Math.min(low[i - 1], low[i - 2], low[i - 3]);
      if (lowestSoFar <= dOpen[i] - a && e > dOpen[i]) { fired.morningRev.add(dk); S.morningRev[i] = long(e, lowestSoFar, e + 1.5 * a); }
      const highestSoFar = Math.max(high[i - 1], high[i - 2], high[i - 3]);
      if (highestSoFar >= dOpen[i] + a && e < dOpen[i]) { fired.morningRev.add(dk); S.morningRev[i] = short(e, highestSoFar, e - 1.5 * a); }
    }
    // 38) Hammer reclaim of SMA20: long lower wick, closes back above SMA20
    if (sma20[i] != null) {
      const body = Math.abs(close[i] - open[i]), loWick = Math.min(close[i], open[i]) - low[i];
      if (loWick > 1.5 * body && low[i] < sma20[i] && e > sma20[i]) S.hammerReclaim[i] = long(e, low[i] - 0.2 * a, e + 2 * a);
      const upWick = high[i] - Math.max(close[i], open[i]);
      if (upWick > 1.5 * body && high[i] > sma20[i] && e < sma20[i]) S.hammerReclaim[i] = short(e, high[i] + 0.2 * a, e - 2 * a);
    }
    // 39) Failed-breakout fade: bar pokes above 20-bar high but closes back below -> short
    if (d20.hi[i] != null) {
      if (high[i] > d20.hi[i] && e < d20.hi[i] && close[i] < open[i]) S.fakeout[i] = short(e, high[i] + 0.2 * a, e - 2 * a);
      else if (low[i] < d20L.lo[i] && e > d20L.lo[i] && close[i] > open[i]) S.fakeout[i] = long(e, low[i] - 0.2 * a, e + 2 * a);
    }
    // 40) NR7 narrow-range break
    {
      const r0 = high[i - 1] - low[i - 1]; let isNR7 = true;
      for (let k = 2; k <= 7; k++) if (high[i - k] - low[i - k] <= r0) isNR7 = false;
      if (isNR7) { if (e > high[i - 1]) S.nr7Break[i] = long(e, low[i - 1], e + 2.5 * (high[i - 1] - low[i - 1])); else if (e < low[i - 1]) S.nr7Break[i] = short(e, high[i - 1], e - 2.5 * (high[i - 1] - low[i - 1])); }
    }

    // ---------- TIME / SESSION ----------
    // 41) Lunch-range (12:00-13:00) break in the afternoon (after 13:00)
    if (p.mins >= 780 && lunch.hi.has(dk)) {
      const rh = lunch.hi.get(dk), rl = lunch.lo.get(dk);
      if (close[i - 1] <= rh && e > rh) S.lunchBrk[i] = long(e, rl, e + 1.2 * (rh - rl));
      else if (close[i - 1] >= rl && e < rl) S.lunchBrk[i] = short(e, rh, e - 1.2 * (rh - rl));
    }
    // 42) Power-hour momentum (15:00-15:45) with trend
    if (p.mins >= 900 && p.mins <= 945) {
      if (up200 && close[i] > open[i] && close[i] > close[i - 1]) S.powerHour[i] = long(e, e - 1.2 * a, e + 1.8 * a);
      else if (dn200 && close[i] < open[i] && close[i] < close[i - 1]) S.powerHour[i] = short(e, e + 1.2 * a, e - 1.8 * a);
    }
    // 43) First-hour extreme fade (10:00-10:30): fade the first-hour high/low back to VWAP
    if (p.mins >= 600 && p.mins <= 630 && fhr.hi.has(dk) && vwap[i] != null) {
      const rh = fhr.hi.get(dk), rl = fhr.lo.get(dk);
      if (e >= rh && close[i] < open[i]) S.firstHrFade[i] = short(e, rh + 0.5 * a, vwap[i] < e ? vwap[i] : e - a);
      else if (e <= rl && close[i] > open[i]) S.firstHrFade[i] = long(e, rl - 0.5 * a, vwap[i] > e ? vwap[i] : e + a);
    }
    // 44) Midday (11:00-14:00) BB mean-reversion: tag band, fade to basis
    if (p.mins >= 660 && p.mins <= 840 && loBB[i] != null) {
      if (low[i] <= loBB[i] && close[i] > open[i]) S.middayMR[i] = long(e, loBB[i] - a, sma20[i]);
      else if (high[i] >= upBB[i] && close[i] < open[i]) S.middayMR[i] = short(e, upBB[i] + a, sma20[i]);
    }
    // 45) Open-drive continuation: first 3 RTH bars all same direction -> ride 4th (09:45 bar)
    if (p.mins === 585) {
      const allUp = close[i - 1] > open[i - 1] && close[i - 2] > open[i - 2] && close[i - 3] > open[i - 3];
      const allDn = close[i - 1] < open[i - 1] && close[i - 2] < open[i - 2] && close[i - 3] < open[i - 3];
      if (allUp && close[i] > open[i]) S.openDrive[i] = long(e, low[i - 3], e + 2 * a);
      else if (allDn && close[i] < open[i]) S.openDrive[i] = short(e, high[i - 3], e - 2 * a);
    }

    // ---------- VOLATILITY / OTHER ----------
    // 46) ATR-expansion break: ATR5 > 1.4 ATR14 + decisive close direction
    if (atr5[i] != null && atr5[i] > 1.4 * a) {
      const rng = high[i] - low[i];
      if (rng > 0 && close[i] >= high[i] - 0.3 * rng) S.atrExpBrk[i] = long(e, low[i], e + 2 * a);
      else if (rng > 0 && close[i] <= low[i] + 0.3 * rng) S.atrExpBrk[i] = short(e, high[i], e - 2 * a);
    }
    // 47) Stdev spike: stdev(20) jumps >30% vs 5 bars ago + direction
    if (dev[i] != null && dev[i - 5] != null && dev[i - 5] > 0 && dev[i] > 1.3 * dev[i - 5]) {
      if (close[i] > open[i] && up200) S.stdevSpike[i] = long(e, e - 1.5 * a, e + 2 * a);
      else if (close[i] < open[i] && dn200) S.stdevSpike[i] = short(e, e + 1.5 * a, e - 2 * a);
    }
    // 48) MACD-hist early turn: hist negative but rising 2 bars (long), positive but falling (short)
    if (hist[i] != null && hist[i - 1] != null && hist[i - 2] != null) {
      if (hist[i] < 0 && hist[i] > hist[i - 1] && hist[i - 1] > hist[i - 2] && up200) S.macdHistTurn[i] = long(e, e - 1.5 * a, e + 2 * a);
      else if (hist[i] > 0 && hist[i] < hist[i - 1] && hist[i - 1] < hist[i - 2] && dn200) S.macdHistTurn[i] = short(e, e + 1.5 * a, e - 2 * a);
    }
    // 49) RSI band-ride: RSI14 holding >55 (bull regime), buy a dip to EMA8
    if (rsi14[i] != null && rsi14[i - 1] != null && ema8[i] != null) {
      if (rsi14[i] > 55 && rsi14[i - 1] > 55 && low[i] <= ema8[i] && e > ema8[i]) S.rsiBandRide[i] = long(e, e - 1.5 * a, e + 2 * a);
      else if (rsi14[i] < 45 && rsi14[i - 1] < 45 && high[i] >= ema8[i] && e < ema8[i]) S.rsiBandRide[i] = short(e, e + 1.5 * a, e - 2 * a);
    }
    // 50) +DI/-DI cross with ADX>20
    if (adx && adx[i] != null && adx[i] > 20 && plusDI && plusDI[i] != null && plusDI[i - 1] != null) {
      if (plusDI[i - 1] <= minusDI[i - 1] && plusDI[i] > minusDI[i]) S.diCross[i] = long(e, e - 1.5 * a, e + 2.5 * a);
      else if (plusDI[i - 1] >= minusDI[i - 1] && plusDI[i] < minusDI[i]) S.diCross[i] = short(e, e + 1.5 * a, e - 2.5 * a);
    }
  }
  return S;
}

// ---------------- report one dataset ----------------
function report(label, bars) {
  const days = new Set(bars.map((b) => dayKeyOf(b.t))).size;
  const S = buildAll(bars);
  const rows = KEYS.map((k) => ({ key: k, name: NAMES[k], r: runSignals(bars, S[k]) }))
    .sort((a, b) => b.r.netPts - a.r.netPts);

  console.log(`\n${"=".repeat(110)}\n${label} — ${days} ET days / ${bars.length} 5m bars. Net shown @5MNQ ($10/pt) AND @1MNQ ($2/pt). Combine: DLL $1000/day, MLL $2000.\n${"=".repeat(110)}`);
  const hdr = "Strategy".padEnd(32) + "Trd".padStart(4) + "Win%".padStart(6) + "PF".padStart(6) +
    "Net@5MNQ".padStart(11) + "Net@1MNQ".padStart(10) + "MaxDD@5".padStart(9) + "WrstDay@5".padStart(11) + "5MNQ".padStart(6) + "1MNQ".padStart(6);
  console.log(hdr); console.log("-".repeat(hdr.length));
  for (const { name, r } of rows) {
    const net5 = r.netPts * 10, net1 = r.netPts * 2, dd5 = r.ddPts * 10, dd1 = r.ddPts * 2;
    const wd5 = Math.abs(r.worstDayPts * 10), wd1 = Math.abs(r.worstDayPts * 2);
    const surv5 = (wd5 < DLL && dd5 < MLL) ? "OK" : (wd5 >= DLL ? "DLL!" : "MLL!");
    const surv1 = (wd1 < DLL && dd1 < MLL) ? "OK" : (wd1 >= DLL ? "DLL!" : "MLL!");
    console.log(
      name.padEnd(32) + String(r.n).padStart(4) + (f(r.winRate) + "%").padStart(6) +
      (r.pf === Infinity ? "inf" : f(r.pf, 2)).padStart(6) +
      ((net5 >= 0 ? "+$" : "-$") + f(Math.abs(net5))).padStart(11) +
      ((net1 >= 0 ? "+$" : "-$") + f(Math.abs(net1))).padStart(10) +
      ("$" + f(dd5)).padStart(9) + ("-$" + f(wd5)).padStart(11) +
      surv5.padStart(6) + surv1.padStart(6)
    );
  }
  return rows;
}

// Exported so power-hour-windows.js (and any future slicer) reuses the EXACT
// same strategy code + exit model — no reimplementation drift.
module.exports = { buildAll, runSignals, runLedger, tally, KEYS, NAMES, loadCsv, dayKeyOf, etParts, CSV_13, DLL, MLL };

async function main() {
  console.log("BATCH-4 LAB — 50 NEW intraday strategies on the 13-day + 58-day charts, @5 MNQ and @1 MNQ.");
  console.log("Fair exit model: RTH entries, flat by 16:00 ET, one position at a time, stop-first on ties. Raw edge (no eval lockout); Combine survival FLAGGED.");

  const bars13 = loadCsv(CSV_13);
  const rows13 = report("13-DAY CHART (MNQ CSV)", bars13);

  let bars58 = null;
  try { bars58 = await Yahoo.fetchBars({ interval: "5m", range: "60d" }); }
  catch (e) {
    console.error(`\nYahoo live fetch failed (${e.message}); falling back to cached data/nq-5m.json`);
    bars58 = JSON.parse(fs.readFileSync(__dirname + "/data/nq-5m.json", "utf8"));
  }
  const rows58 = report("58-DAY CHART (Yahoo NQ=F 5m)", bars58);

  // cross-sample hold-up: which 13d winners survive on 58d
  const top13 = rows13.slice(0, 10).map((x) => x.key);
  const m58 = new Map(rows58.map((x) => [x.key, x.r]));
  console.log(`\n${"=".repeat(110)}\nHOLD-UP — top 10 by 13-day net, did the edge survive the 58-day out-of-sample run?\n${"=".repeat(110)}`);
  console.log("Strategy".padEnd(32) + "13d PF".padStart(8) + "58d PF".padStart(8) + "13d Net@5".padStart(11) + "58d Net@5".padStart(11) + "Verdict".padStart(14));
  for (const k of top13) {
    const a = rows13.find((x) => x.key === k).r, b = m58.get(k);
    const held = b && b.pf >= 1.3 && b.netPts > 0;
    console.log(
      NAMES[k].padEnd(32) + (a.pf === Infinity ? "inf" : f(a.pf, 2)).padStart(8) + (b.pf === Infinity ? "inf" : f(b.pf, 2)).padStart(8) +
      ((a.netPts * 10 >= 0 ? "+$" : "-$") + f(Math.abs(a.netPts * 10))).padStart(11) +
      ((b.netPts * 10 >= 0 ? "+$" : "-$") + f(Math.abs(b.netPts * 10))).padStart(11) +
      (held ? "EDGE HOLDS" : "faded").padStart(14)
    );
  }
  // also: which strategies are positive AND PF>1.5 on BOTH samples
  const both = KEYS.filter((k) => {
    const a = rows13.find((x) => x.key === k).r, b = m58.get(k);
    return a.netPts > 0 && a.pf >= 1.5 && b && b.netPts > 0 && b.pf >= 1.5;
  });
  console.log(`\nPositive + PF>=1.5 on BOTH 13d AND 58d: ${both.length ? both.map((k) => NAMES[k].replace(/^\d+\.\s*/, "")).join(", ") : "NONE"}`);
  console.log(`\nCaveat: 13d = single-regime fingerprint (idea screen). 58d (Apr-Jun 2026) = the real out-of-sample test, but still one quarter, one instrument. Not multi-year proof. None of this beats the locked mean-rev v1.1 until it clears PF>1.5 across regime-diverse data.`);
}

if (require.main === module) main().catch((e) => { console.error("lab-new4 error:", e.stack || e.message); process.exit(1); });
