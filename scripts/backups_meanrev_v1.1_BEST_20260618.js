// =============================================================
//  meanrev.js — v1.1 mean-reversion signal logic (the LOCKED keeper),
//  ported 1:1 from meanrev_v1.pine. Framework-free so it is shared by:
//    - the browser panel (public/app.js -> window.MeanRev)
//    - the Discord watcher (watcher.js -> require/globalThis.MeanRev)
//    - the future TopstepX extension content script
//
//  Edge (fade a stretch back to the mean, on the RECLAIM):
//    LONG  = price closed back ABOVE the lower band (crossover) within
//            `confirmBars` of an oversold stretch (close<=lowerBB &
//            RSI(2)<=rsiOS), in a RANGING regime (ADX<adxMax), with the
//            higher trend up (close>EMA200), during RTH.
//    SHORT = mirror.
//  Stop = atrStop * ATR(14).  Target = the mean (BB basis).
//
//  Consumes bars = [{ t, o, h, l, c, v }] with t = epoch SECONDS.
// =============================================================
(function (root) {
  "use strict";

  const I = root.Indicators;
  if (!I) throw new Error("meanrev.js requires indicators.js to load first");

  // The LOCKED v1.1 config (matches meanrev_v1.pine defaults).
  const CONFIG = {
    bbLen: 20, bbMult: 2.0,
    rsiLen: 2, rsiOS: 10, rsiOB: 90,
    adxLen: 14, adxMax: 25,
    trendLen: 200,
    atrLen: 14, atrStop: 1.0,
    confirmBars: 3,
    pointValueNQ: 20, pointValueMNQ: 2,
    rthStart: 9 * 60 + 30, // 09:30 ET
    rthEnd: 16 * 60,       // 16:00 ET
  };

  // True if the epoch-second timestamp falls inside RTH (Mon-Fri, ET).
  function isInRTH(epochSec) {
    const d = new Date(epochSec * 1000);
    const et = new Date(d.toLocaleString("en-US", { timeZone: "America/New_York" }));
    const day = et.getDay();
    if (day === 0 || day === 6) return false;
    const mins = et.getHours() * 60 + et.getMinutes();
    return mins >= CONFIG.rthStart && mins < CONFIG.rthEnd;
  }

  // Evaluate the v1.1 signal at bar index `at` (default: last bar).
  // For live use pass the last CLOSED bar (e.g. bars.length-2) so a
  // still-forming bar can't flicker the signal.
  function computeMeanRev(bars, at) {
    const n = bars.length;
    const i = (at == null) ? n - 1 : at;
    const close = bars.map((b) => b.c);
    const high = bars.map((b) => b.h);
    const low = bars.map((b) => b.l);

    const basis = I.sma(close, CONFIG.bbLen);
    const dev = I.stdev(close, CONFIG.bbLen);
    const lowerBB = basis.map((v, k) => (v == null ? null : v - CONFIG.bbMult * dev[k]));
    const upperBB = basis.map((v, k) => (v == null ? null : v + CONFIG.bbMult * dev[k]));
    const rsi = I.rsi(close, CONFIG.rsiLen);
    const { adx } = I.dmi(high, low, close, CONFIG.adxLen, CONFIG.adxLen);
    const ema200 = I.ema(close, CONFIG.trendLen);
    const atr = I.atr(high, low, close, CONFIG.atrLen);

    const blank = (reason) => ({
      signal: "WAIT", dir: 0, reason,
      price: close[i], barTime: bars[i] ? bars[i].t : null,
      basis: basis[i], lowerBB: lowerBB[i], upperBB: upperBB[i],
      rsi: rsi[i], adx: adx[i], atr: atr[i],
      trend: ema200[i] != null ? (close[i] > ema200[i] ? "UP" : "DOWN") : "?",
      ranging: adx[i] != null ? adx[i] < CONFIG.adxMax : false,
      inSession: bars[i] ? isInRTH(bars[i].t) : false,
    });

    if (i < 1 || basis[i] == null || ema200[i] == null || adx[i] == null || atr[i] == null) {
      return blank("not enough history");
    }

    const inSession = isInRTH(bars[i].t);
    const ranging = adx[i] < CONFIG.adxMax;
    const upBias = close[i] > ema200[i];
    const dnBias = close[i] < ema200[i];

    // Stretch states (band + RSI exhaustion) over recent bars.
    const stretchLong = close.map((c, k) =>
      lowerBB[k] != null && rsi[k] != null && c <= lowerBB[k] && rsi[k] <= CONFIG.rsiOS);
    const stretchShort = close.map((c, k) =>
      upperBB[k] != null && rsi[k] != null && c >= upperBB[k] && rsi[k] >= CONFIG.rsiOB);

    // Reclaim = price crosses back inside the band within confirmBars of a stretch.
    const xUp = I.crossover(close, lowerBB);   // closed back above lower band
    const xDn = I.crossunder(close, upperBB);  // closed back below upper band
    const reclaimLong = xUp[i] && I.barsSince(stretchLong, i) <= CONFIG.confirmBars;
    const reclaimShort = xDn[i] && I.barsSince(stretchShort, i) <= CONFIG.confirmBars;

    const base = blank("");
    base.basis = basis[i]; base.lowerBB = lowerBB[i]; base.upperBB = upperBB[i];
    base.rsi = rsi[i]; base.adx = adx[i]; base.atr = atr[i];
    base.ranging = ranging; base.inSession = inSession;

    if (!inSession) return { ...base, signal: "CLOSED", reason: "outside RTH (09:30-16:00 ET)" };
    if (!ranging) return { ...base, signal: "WAIT", reason: `ADX ${adx[i].toFixed(0)} >= ${CONFIG.adxMax} - market is TRENDING, don't fade` };

    if (reclaimLong && upBias) {
      const entry = close[i];
      const stop = entry - CONFIG.atrStop * atr[i];
      const target = basis[i];
      return {
        ...base, signal: "BUY", dir: 1, entry, stop, target,
        stopPts: entry - stop, tgtPts: target - entry,
        reason: `Price reclaimed the LOWER band after RSI(2) washout (${rsi[i].toFixed(0)}) in a ranging, up-trending market -> FADE LONG to the mean`,
      };
    }
    if (reclaimShort && dnBias) {
      const entry = close[i];
      const stop = entry + CONFIG.atrStop * atr[i];
      const target = basis[i];
      return {
        ...base, signal: "SELL", dir: -1, entry, stop, target,
        stopPts: stop - entry, tgtPts: entry - target,
        reason: `Price reclaimed the UPPER band after RSI(2) spike (${rsi[i].toFixed(0)}) in a ranging, down-trending market -> FADE SHORT to the mean`,
      };
    }
    return { ...base, signal: "WAIT", reason: "no reclaim setup on the last closed bar" };
  }

  root.MeanRev = { CONFIG, isInRTH, computeMeanRev };
})(typeof window !== "undefined" ? window : globalThis);
