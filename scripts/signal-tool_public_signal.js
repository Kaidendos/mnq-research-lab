// =============================================================
//  signal.js — v5 BEST strategy logic, ported from Pine to JS.
//  Consumes window.Indicators. Produces the panel state the UI shows.
//  Reused as-is by the future TopstepX extension content script.
//
//  🔒 LOCKED v5 BEST config (found 2026-06-17):
//     MACD lookback 2, RSI long floor 60, RSI short ceiling 32,
//     ADX>20 regime, EMA200 trend, BB 12/2, ADR-20 stops/targets.
// =============================================================
(function (root) {
  "use strict";

  const CONFIG = {
    bbLen: 12, bbMult: 2.0,
    macdFast: 12, macdSlow: 26, macdSig: 9,
    rsiLen: 7,
    rsiLongMin: 60,   // go long only if RSI >= this
    rsiShortMax: 32,  // go short only if RSI <= this
    macdLookback: 2,  // a MACD cross within the last N bars still counts
    adxLen: 14, adxMin: 20,
    trendLen: 200,
    adrLen: 20,
    stopPct: 0.10, tgtPct: 0.15,
    pointValueNQ: 20, pointValueMNQ: 2,
    sessionStart: "09:30", sessionEnd: "16:00", // RTH, ET
  };

  // Is the given epoch-seconds timestamp inside RTH (09:30-16:00 ET)?
  function isInRTH(epochSec) {
    const d = new Date(epochSec * 1000);
    const et = new Date(
      d.toLocaleString("en-US", { timeZone: "America/New_York" })
    );
    const day = et.getDay(); // 0 Sun .. 6 Sat
    if (day === 0 || day === 6) return false;
    const mins = et.getHours() * 60 + et.getMinutes();
    return mins >= 9 * 60 + 30 && mins < 16 * 60;
  }

  // ADR-20 in points from an array of daily bars {h,l}.
  function computeADR(dailyBars, len) {
    const ranges = dailyBars
      .filter((b) => b.h != null && b.l != null)
      .map((b) => b.h - b.l);
    const slice = ranges.slice(-len);
    if (slice.length === 0) return null;
    return slice.reduce((a, b) => a + b, 0) / slice.length;
  }

  // Main: bars = 5-min array {t,o,h,l,c,v}; adrPoints from daily data.
  function computeSignal(bars, adrPoints) {
    const I = root.Indicators;
    const n = bars.length;
    if (n < CONFIG.trendLen + 5) {
      return { signal: "NO DATA", reason: "not enough bars", bars: n };
    }
    const close = bars.map((b) => b.c);
    const high = bars.map((b) => b.h);
    const low = bars.map((b) => b.l);

    const basis = I.sma(close, CONFIG.bbLen);
    const dev = I.stdev(close, CONFIG.bbLen);
    const upperBB = basis.map((v, i) => (v == null ? null : v + CONFIG.bbMult * dev[i]));
    const lowerBB = basis.map((v, i) => (v == null ? null : v - CONFIG.bbMult * dev[i]));
    const { macdLine, signalLine } = I.macd(close, CONFIG.macdFast, CONFIG.macdSlow, CONFIG.macdSig);
    const rsi = I.rsi(close, CONFIG.rsiLen);
    const { adx } = I.dmi(high, low, close, CONFIG.adxLen, CONFIG.adxLen);
    const ema200 = I.ema(close, CONFIG.trendLen);
    const crossUp = I.crossover(macdLine, signalLine);
    const crossDn = I.crossunder(macdLine, signalLine);

    const i = n - 1; // evaluate on the latest bar
    const c = close[i];

    const macdUpOK = I.barsSince(crossUp, i) <= CONFIG.macdLookback - 1 && macdLine[i] > signalLine[i];
    const macdDnOK = I.barsSince(crossDn, i) <= CONFIG.macdLookback - 1 && macdLine[i] < signalLine[i];

    const primaryLong = macdUpOK && rsi[i] > CONFIG.rsiLongMin && c < upperBB[i];
    const primaryShort = macdDnOK && rsi[i] < CONFIG.rsiShortMax && c > lowerBB[i];

    const regimeOK = adx[i] != null && adx[i] > CONFIG.adxMin;
    const upTrend = c > ema200[i];
    const dnTrend = c < ema200[i];
    const inSession = isInRTH(bars[i].t);

    const longCond = primaryLong && regimeOK && inSession && upTrend;
    const shortCond = primaryShort && regimeOK && inSession && dnTrend;

    let signal;
    if (longCond) signal = "BUY";
    else if (shortCond) signal = "SELL";
    else if (!inSession) signal = "CLOSED";
    else signal = "WAIT";

    const bias =
      c > basis[i] && macdLine[i] > signalLine[i] ? "BULLISH"
      : c < basis[i] && macdLine[i] < signalLine[i] ? "BEARISH"
      : "NEUTRAL";

    const stopPts = adrPoints == null ? null : adrPoints * CONFIG.stopPct;
    const tgtPts = adrPoints == null ? null : adrPoints * CONFIG.tgtPct;

    // Entry/stop/target levels for whichever side is (or would be) signalled.
    let entry = null, stop = null, target = null, dir = null;
    if (signal === "BUY" || (signal === "WAIT" && bias === "BULLISH")) {
      dir = "LONG";
      entry = c;
      if (stopPts != null) { stop = c - stopPts; target = c + tgtPts; }
    } else if (signal === "SELL" || (signal === "WAIT" && bias === "BEARISH")) {
      dir = "SHORT";
      entry = c;
      if (stopPts != null) { stop = c + stopPts; target = c - tgtPts; }
    }

    const riskMNQ = stopPts == null ? null : stopPts * CONFIG.pointValueMNQ * 2; // 2 MNQ
    const rewardMNQ = tgtPts == null ? null : tgtPts * CONFIG.pointValueMNQ * 2;

    return {
      signal, bias, dir, entry, stop, target,
      price: c,
      rsi: rsi[i], adx: adx[i],
      macdUp: macdLine[i] > signalLine[i],
      trend: c > ema200[i] ? "UP" : "DOWN",
      inSession,
      regimeOK,
      adrPoints, stopPts, tgtPts,
      riskMNQ, rewardMNQ,
      barTime: bars[i].t,
      bars: n,
    };
  }

  root.SignalEngine = { CONFIG, computeSignal, computeADR, isInRTH };
})(typeof window !== "undefined" ? window : globalThis);
