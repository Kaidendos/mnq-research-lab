// =============================================================
//  simple.js — "The Simple Strategy" (Heitkoetter) signal logic, ported
//  1:1 from the simple_strategy_v3 / v5 Pine scripts. Framework-free so it
//  can be shared by the backtest harness, the Discord watcher, and the
//  future TopstepX extension content script (same pattern as meanrev.js /
//  orb.js).
//
//  Edge: a MACD cross (within `macdLookback` bars, still onside) in the
//  trend direction (close vs EMA200), with RSI(7) onside and price inside
//  the Bollinger band, in a trending regime (ADX > adxMin), during RTH.
//  Stop / target are a % of the 20-day ADR. Stop latches to breakeven at +1R.
//
//  The three locked TradingView versions are presets (PRESETS):
//    v5      — LOCKED BEST  : lookback 2, RSI 60/32, target 20% ADR
//    v3      — LOCKED base  : cross-bar only, RSI 50/50, target 15% ADR
//    v5loose — freq A/B knob: lookback 2, RSI 50/50, target 20% ADR
//
//  Consumes bars = [{ t, o, h, l, c, v }] with t = epoch SECONDS, ascending.
// =============================================================
(function (root) {
  "use strict";

  const I = root.Indicators;
  if (!I) throw new Error("simple.js requires indicators.js to load first");

  // Shared core (matches v3/v5 Pine inputs). The per-version knobs live in
  // PRESETS and are merged over this by prepare()/computeSimple().
  const CONFIG = {
    bbLen: 12, bbMult: 2.0,
    macdFast: 12, macdSlow: 26, macdSig: 9,
    rsiLen: 7,
    adxLen: 14, adxMin: 20,
    trendLen: 200,
    adrLen: 20, stopPct: 0.10, tgtPct: 0.20,
    // version knobs (defaults = v5 BEST):
    macdLookback: 2, rsiLongMin: 60, rsiShortMax: 32, useSetup2: false,
    // risk management:
    dayLoss: 1000, useBE: true, beTrigR: 1.0,
    pointValueNQ: 20, pointValueMNQ: 2,
    rthStart: 9 * 60 + 30, // 09:30 ET
    rthEnd: 16 * 60,       // 16:00 ET
  };

  // The 3 best TradingView versions, as parameter overrides.
  const PRESETS = {
    v5:      { label: "Simple v5 (BEST 60/32)", macdLookback: 2, rsiLongMin: 60, rsiShortMax: 32, tgtPct: 0.20, useSetup2: false },
    v3:      { label: "Simple v3 (LOCKED 50/50)", macdLookback: 1, rsiLongMin: 50, rsiShortMax: 50, tgtPct: 0.15, useSetup2: false },
    v5loose: { label: "Simple v5 looser (50/50)", macdLookback: 2, rsiLongMin: 50, rsiShortMax: 50, tgtPct: 0.20, useSetup2: false },
  };

  // ET calendar-day key for a bar (groups bars into days for ADR + EOD flat).
  function dayKeyOf(epochSec) {
    const et = new Date(new Date(epochSec * 1000).toLocaleString("en-US", { timeZone: "America/New_York" }));
    return `${et.getFullYear()}-${et.getMonth()}-${et.getDate()}`;
  }

  // True if the epoch-second timestamp falls inside RTH (Mon-Fri, ET).
  function isInRTH(epochSec) {
    const et = new Date(new Date(epochSec * 1000).toLocaleString("en-US", { timeZone: "America/New_York" }));
    const day = et.getDay();
    if (day === 0 || day === 6) return false;
    const mins = et.getHours() * 60 + et.getMinutes();
    return mins >= CONFIG.rthStart && mins < CONFIG.rthEnd;
  }

  // Average Daily Range (in points) per ET day, computed from the intraday
  // bars themselves (ProjectX gives no daily series). Pine uses a daily
  // request.security with lookahead OFF, so the ADR available on day D is
  // the mean range of the PRIOR completed days only (current day excluded).
  //
  // Caveat: ET-calendar grouping splits the overnight session at midnight,
  // so this slightly understates a true CME daily bar. It is applied
  // identically to all 3 versions, so the comparison stays fair.
  function adrByDay(bars, adrLen) {
    const order = [];
    const hi = new Map();
    const lo = new Map();
    for (const b of bars) {
      const k = dayKeyOf(b.t);
      if (!hi.has(k)) { order.push(k); hi.set(k, b.h); lo.set(k, b.l); }
      else { hi.set(k, Math.max(hi.get(k), b.h)); lo.set(k, Math.min(lo.get(k), b.l)); }
    }
    const ranges = order.map((k) => hi.get(k) - lo.get(k));
    const out = new Map();
    for (let d = 0; d < order.length; d++) {
      const start = Math.max(0, d - adrLen);
      const prior = ranges.slice(start, d); // strictly days before d
      out.set(order[d], prior.length ? prior.reduce((a, b) => a + b, 0) / prior.length : null);
    }
    return out;
  }

  // Precompute every indicator series ONCE for a bar set. The backtest passes
  // the result to computeSimple() for each bar so the replay is O(n), not
  // O(n^2). Live callers can skip this — computeSimple() builds it on demand.
  function prepare(bars, opts) {
    const C = { ...CONFIG, ...(opts || {}) };
    const close = bars.map((b) => b.c);
    const high = bars.map((b) => b.h);
    const low = bars.map((b) => b.l);
    const basis = I.sma(close, C.bbLen);
    const dev = I.stdev(close, C.bbLen);
    const upperBB = basis.map((v, k) => (v == null ? null : v + C.bbMult * dev[k]));
    const lowerBB = basis.map((v, k) => (v == null ? null : v - C.bbMult * dev[k]));
    const { macdLine, signalLine } = I.macd(close, C.macdFast, C.macdSlow, C.macdSig);
    const rsi = I.rsi(close, C.rsiLen);
    const { adx } = I.dmi(high, low, close, C.adxLen, C.adxLen);
    const ema200 = I.ema(close, C.trendLen);
    const crossUp = I.crossover(macdLine, signalLine);
    const crossDn = I.crossunder(macdLine, signalLine);
    const closeXupBasis = I.crossover(close, basis);
    const closeXdnBasis = I.crossunder(close, basis);
    return {
      C, close, high, low, basis, upperBB, lowerBB,
      macdLine, signalLine, rsi, adx, ema200,
      crossUp, crossDn, closeXupBasis, closeXdnBasis,
      adr: adrByDay(bars, C.adrLen),
    };
  }

  // Evaluate the signal at bar index `at` (default: last bar). For live use
  // pass the last CLOSED bar so a still-forming bar can't flicker the signal.
  // `pre` (from prepare()) is optional; built on demand if omitted.
  function computeSimple(bars, at, opts, pre) {
    pre = pre || prepare(bars, opts);
    const C = pre.C;
    const n = bars.length;
    const i = (at == null) ? n - 1 : at;

    const px = pre.close[i];
    const adr = bars[i] ? pre.adr.get(dayKeyOf(bars[i].t)) : null;
    const inSession = bars[i] ? isInRTH(bars[i].t) : false;

    const blank = (signal, reason) => ({
      signal, dir: 0, reason,
      price: px, barTime: bars[i] ? bars[i].t : null,
      basis: pre.basis[i], upperBB: pre.upperBB[i], lowerBB: pre.lowerBB[i],
      rsi: pre.rsi[i], adx: pre.adx[i], adr,
      trend: pre.ema200[i] != null ? (px > pre.ema200[i] ? "UP" : "DOWN") : "?",
      inSession,
    });

    if (i < 1 || pre.basis[i] == null || pre.ema200[i] == null ||
        pre.adx[i] == null || pre.macdLine[i] == null || pre.signalLine[i] == null ||
        pre.rsi[i] == null) {
      return blank("WAIT", "not enough history");
    }
    if (adr == null) return blank("WAIT", "no ADR yet (need a prior completed day)");
    if (!inSession) return blank("CLOSED", "outside RTH (09:30-16:00 ET)");

    const regimeOK = pre.adx[i] > C.adxMin;
    if (!regimeOK) return blank("WAIT", `ADX ${pre.adx[i].toFixed(0)} <= ${C.adxMin} - no trend regime`);

    const upTrend = px > pre.ema200[i];
    const dnTrend = px < pre.ema200[i];
    const stopPts = adr * C.stopPct;
    const tgtPts = adr * C.tgtPct;

    // Primary setup (v3 core + v5 lookback knob).
    const macdUpOK = I.barsSince(pre.crossUp, i) <= C.macdLookback - 1 && pre.macdLine[i] > pre.signalLine[i];
    const macdDnOK = I.barsSince(pre.crossDn, i) <= C.macdLookback - 1 && pre.macdLine[i] < pre.signalLine[i];
    const primaryLong = macdUpOK && pre.rsi[i] > C.rsiLongMin && px < pre.upperBB[i];
    const primaryShort = macdDnOK && pre.rsi[i] < C.rsiShortMax && px > pre.lowerBB[i];

    // Optional setup #2: BB-midline reclaim in the trend direction.
    const setup2Long = C.useSetup2 && pre.closeXupBasis[i] && pre.macdLine[i] > pre.signalLine[i] && pre.rsi[i] > C.rsiLongMin;
    const setup2Short = C.useSetup2 && pre.closeXdnBasis[i] && pre.macdLine[i] < pre.signalLine[i] && pre.rsi[i] < C.rsiShortMax;

    const base = blank("WAIT", "no setup on the last closed bar");

    if ((primaryLong || setup2Long) && upTrend) {
      return {
        ...base, signal: "BUY", dir: 1,
        entry: px, stop: px - stopPts, target: px + tgtPts,
        stopPts, tgtPts, beTrigPts: stopPts * C.beTrigR, useBE: C.useBE,
        reason: `MACD cross up onside, RSI(7) ${pre.rsi[i].toFixed(0)} > ${C.rsiLongMin}, inside band, up-trend, ADX ${pre.adx[i].toFixed(0)} -> LONG`,
      };
    }
    if ((primaryShort || setup2Short) && dnTrend) {
      return {
        ...base, signal: "SELL", dir: -1,
        entry: px, stop: px + stopPts, target: px - tgtPts,
        stopPts, tgtPts, beTrigPts: stopPts * C.beTrigR, useBE: C.useBE,
        reason: `MACD cross down onside, RSI(7) ${pre.rsi[i].toFixed(0)} < ${C.rsiShortMax}, inside band, down-trend, ADX ${pre.adx[i].toFixed(0)} -> SHORT`,
      };
    }
    return base;
  }

  root.Simple = { CONFIG, PRESETS, isInRTH, dayKeyOf, adrByDay, prepare, computeSimple };
})(typeof window !== "undefined" ? window : globalThis);
