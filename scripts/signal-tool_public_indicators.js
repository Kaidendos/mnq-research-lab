// =============================================================
//  indicators.js — pure technical-indicator math (no DOM, no deps)
//  Ported from the v5 Pine strategy so the numbers match TradingView
//  closely. Framework-free on purpose: this exact file will be reused
//  by the future TopstepX Chrome extension content script.
//
//  All functions take a numeric array (e.g. closes) and return an
//  array of the same length, with `null` for bars that don't yet have
//  enough history. Wilder's smoothing (RMA) is used for RSI/ADX to
//  match Pine's ta.rsi / ta.dmi.
// =============================================================
(function (root) {
  "use strict";

  // Simple moving average.
  function sma(src, len) {
    const out = new Array(src.length).fill(null);
    let sum = 0;
    for (let i = 0; i < src.length; i++) {
      sum += src[i];
      if (i >= len) sum -= src[i - len];
      if (i >= len - 1) out[i] = sum / len;
    }
    return out;
  }

  // Population standard deviation over a window (matches Pine ta.stdev).
  function stdev(src, len) {
    const out = new Array(src.length).fill(null);
    for (let i = len - 1; i < src.length; i++) {
      let mean = 0;
      for (let j = i - len + 1; j <= i; j++) mean += src[j];
      mean /= len;
      let v = 0;
      for (let j = i - len + 1; j <= i; j++) {
        const d = src[j] - mean;
        v += d * d;
      }
      out[i] = Math.sqrt(v / len);
    }
    return out;
  }

  // Exponential moving average. Seeded with the SMA of the first `len`
  // values (stable; converges to Pine's ta.ema within a few bars).
  function ema(src, len) {
    const out = new Array(src.length).fill(null);
    const alpha = 2 / (len + 1);
    let prev = null;
    let sum = 0;
    for (let i = 0; i < src.length; i++) {
      if (i < len - 1) {
        sum += src[i];
        continue;
      }
      if (prev === null) {
        sum += src[i];
        prev = sum / len; // seed = SMA of first window
      } else {
        prev = alpha * src[i] + (1 - alpha) * prev;
      }
      out[i] = prev;
    }
    return out;
  }

  // Wilder's smoothing / running moving average (Pine ta.rma).
  // alpha = 1/len. Seeded with SMA of first `len`.
  function rma(src, len) {
    const out = new Array(src.length).fill(null);
    let prev = null;
    let sum = 0;
    for (let i = 0; i < src.length; i++) {
      const x = src[i] == null ? 0 : src[i];
      if (i < len - 1) {
        sum += x;
        continue;
      }
      if (prev === null) {
        sum += x;
        prev = sum / len;
      } else {
        prev = (prev * (len - 1) + x) / len;
      }
      out[i] = prev;
    }
    return out;
  }

  // RSI via Wilder's smoothing (matches Pine ta.rsi).
  function rsi(close, len) {
    const n = close.length;
    const gain = new Array(n).fill(0);
    const loss = new Array(n).fill(0);
    for (let i = 1; i < n; i++) {
      const ch = close[i] - close[i - 1];
      gain[i] = ch > 0 ? ch : 0;
      loss[i] = ch < 0 ? -ch : 0;
    }
    const ag = rma(gain, len);
    const al = rma(loss, len);
    const out = new Array(n).fill(null);
    for (let i = 0; i < n; i++) {
      if (ag[i] == null || al[i] == null) continue;
      if (al[i] === 0) {
        out[i] = 100;
      } else {
        const rs = ag[i] / al[i];
        out[i] = 100 - 100 / (1 + rs);
      }
    }
    return out;
  }

  // MACD line, signal line, histogram (Pine ta.macd uses ta.ema).
  function macd(close, fast, slow, sig) {
    const ef = ema(close, fast);
    const es = ema(close, slow);
    const macdLine = close.map((_, i) =>
      ef[i] == null || es[i] == null ? null : ef[i] - es[i]
    );
    // signal = ema of the (non-null) macd line; compute on the compacted
    // series then map back to original indices.
    const compact = [];
    const idxMap = [];
    for (let i = 0; i < macdLine.length; i++) {
      if (macdLine[i] != null) {
        compact.push(macdLine[i]);
        idxMap.push(i);
      }
    }
    const sigCompact = ema(compact, sig);
    const signalLine = new Array(close.length).fill(null);
    for (let k = 0; k < idxMap.length; k++) signalLine[idxMap[k]] = sigCompact[k];
    const hist = macdLine.map((v, i) =>
      v == null || signalLine[i] == null ? null : v - signalLine[i]
    );
    return { macdLine, signalLine, hist };
  }

  // ADX / DMI (Pine ta.dmi). Returns { plusDI, minusDI, adx }.
  function dmi(high, low, close, diLen, adxLen) {
    const n = high.length;
    const tr = new Array(n).fill(0);
    const plusDM = new Array(n).fill(0);
    const minusDM = new Array(n).fill(0);
    for (let i = 1; i < n; i++) {
      const up = high[i] - high[i - 1];
      const dn = low[i - 1] - low[i];
      plusDM[i] = up > dn && up > 0 ? up : 0;
      minusDM[i] = dn > up && dn > 0 ? dn : 0;
      const tr1 = high[i] - low[i];
      const tr2 = Math.abs(high[i] - close[i - 1]);
      const tr3 = Math.abs(low[i] - close[i - 1]);
      tr[i] = Math.max(tr1, tr2, tr3);
    }
    const trN = rma(tr, diLen);
    const plusN = rma(plusDM, diLen);
    const minusN = rma(minusDM, diLen);
    const plusDI = new Array(n).fill(null);
    const minusDI = new Array(n).fill(null);
    const dx = new Array(n).fill(null);
    for (let i = 0; i < n; i++) {
      if (trN[i] == null || trN[i] === 0) continue;
      plusDI[i] = (100 * plusN[i]) / trN[i];
      minusDI[i] = (100 * minusN[i]) / trN[i];
      const sum = plusDI[i] + minusDI[i];
      dx[i] = sum === 0 ? 0 : (100 * Math.abs(plusDI[i] - minusDI[i])) / sum;
    }
    const adx = rma(dx.map((v) => (v == null ? 0 : v)), adxLen);
    for (let i = 0; i < n; i++) if (dx[i] == null) adx[i] = null;
    return { plusDI, minusDI, adx };
  }

  // Average True Range via Wilder's smoothing (matches Pine ta.atr).
  function atr(high, low, close, len) {
    const n = high.length;
    const tr = new Array(n).fill(0);
    for (let i = 0; i < n; i++) {
      if (i === 0) { tr[i] = high[i] - low[i]; continue; }
      const tr1 = high[i] - low[i];
      const tr2 = Math.abs(high[i] - close[i - 1]);
      const tr3 = Math.abs(low[i] - close[i - 1]);
      tr[i] = Math.max(tr1, tr2, tr3);
    }
    return rma(tr, len);
  }

  // Bars since the most recent `true` in a boolean array, evaluated at
  // index i. Returns a large number if never true. (Pine ta.barssince)
  function barsSince(condArr, i) {
    for (let k = i; k >= 0; k--) if (condArr[k]) return i - k;
    return 1e9;
  }

  // Crossover/crossunder boolean arrays for series a vs b.
  function crossover(a, b) {
    const out = new Array(a.length).fill(false);
    for (let i = 1; i < a.length; i++) {
      if (a[i] == null || b[i] == null || a[i - 1] == null || b[i - 1] == null) continue;
      out[i] = a[i - 1] <= b[i - 1] && a[i] > b[i];
    }
    return out;
  }
  function crossunder(a, b) {
    const out = new Array(a.length).fill(false);
    for (let i = 1; i < a.length; i++) {
      if (a[i] == null || b[i] == null || a[i - 1] == null || b[i - 1] == null) continue;
      out[i] = a[i - 1] >= b[i - 1] && a[i] < b[i];
    }
    return out;
  }

  root.Indicators = {
    sma, stdev, ema, rma, rsi, macd, dmi, atr, barsSince, crossover, crossunder,
  };
})(typeof window !== "undefined" ? window : globalThis);
