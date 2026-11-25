// =============================================================
//  lab-new.js — NEW-STRATEGY R&D on the 13-DAY chart ONLY.
//
//  Invents and tests 10 NEW intraday strategies (distinct edges, not param
//  tweaks of the existing MeanRev/ORB/Simple). 5-min NQ, RTH entries only,
//  flat by 16:00 ET, one position at a time, stop-first on ties — identical
//  exit fairness across all 10 so the comparison is clean.
//
//  Small-sample by design: 13 days = a few trades each. This is an idea
//  generator / leaderboard, NOT proof. Promote winners to multi-sample
//  validation (backtest-lab.js) before trusting them.
//
//  DATA-ONLY / TopStep-compliant: reads a local CSV, never places an order.
//  Run:  node lab-new.js
// =============================================================
"use strict";

const fs = require("fs");
require("./public/indicators.js");
const I = globalThis.Indicators;

const CSV_13 = "C:\\Users\\kaide\\Downloads\\CME_MINI_DL_MNQ1!, 5.csv";
const PV_MNQ = 2;
const f = (x, d = 0) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));

// ---- bar IO + ET time helpers ----
function loadCsv(p) {
  const rows = fs.readFileSync(p, "utf8").trim().split(/\r?\n/);
  const out = [];
  for (let i = 1; i < rows.length; i++) {
    const c = rows[i].split(",");
    const t = +c[0];
    if (!t) continue;
    out.push({ t, o: +c[1], h: +c[2], l: +c[3], c: +c[4], v: +(c[5] || 0) });
  }
  out.sort((a, b) => a.t - b.t);
  return out;
}
function etParts(s) {
  const e = new Date(new Date(s * 1000).toLocaleString("en-US", { timeZone: "America/New_York" }));
  return { day: e.getDay(), mins: e.getHours() * 60 + e.getMinutes(), k: `${e.getFullYear()}-${e.getMonth()}-${e.getDate()}` };
}
const dayKeyOf = (s) => etParts(s).k;
const RTH_START = 570, RTH_END = 960; // 09:30 .. 16:00 ET
function isInRTH(s) { const p = etParts(s); return p.day !== 0 && p.day !== 6 && p.mins >= RTH_START && p.mins < RTH_END; }

// ---- exit sim: flat by 16:00 ET / day change, stop-first on ties ----
function simulateTrade(bars, entryIdx, sig) {
  const isLong = sig.dir === 1, entry = sig.entry, startDay = dayKeyOf(bars[entryIdx].t);
  for (let k = entryIdx + 1; k < bars.length; k++) {
    if (dayKeyOf(bars[k].t) !== startDay || !isInRTH(bars[k].t)) {
      const px = bars[k - 1].c;
      return { pts: isLong ? px - entry : entry - px, exit: "eod", exitIdx: k - 1 };
    }
    const b = bars[k];
    if (isLong ? b.l <= sig.stop : b.h >= sig.stop) return { pts: isLong ? sig.stop - entry : entry - sig.stop, exit: "stop", exitIdx: k };
    if (isLong ? b.h >= sig.target : b.l <= sig.target) return { pts: isLong ? sig.target - entry : entry - sig.target, exit: "target", exitIdx: k };
  }
  const px = bars[bars.length - 1].c;
  return { pts: isLong ? px - entry : entry - px, exit: "end", exitIdx: bars.length - 1 };
}
function runSignals(bars, sig) {
  const trades = [];
  let i = 1;
  while (i < bars.length) {
    if (sig[i] && isInRTH(bars[i].t)) { const r = simulateTrade(bars, i, sig[i]); trades.push({ date: dayKeyOf(bars[i].t), pts: r.pts }); i = r.exitIdx + 1; }
    else i++;
  }
  return tally(trades);
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
  return {
    n: trades.length, wins: wins.length, winRate: trades.length ? (wins.length / trades.length) * 100 : 0,
    pf: gL > 0 ? gW / gL : (gW > 0 ? Infinity : 0), netPts, ddPts: maxDD, worstDayPts, maxLossStreak,
    avgWin: wins.length ? gW / wins.length : 0, avgLoss: (trades.length - wins.length) ? gL / (trades.length - wins.length) : 0,
  };
}

// ---- shared precompute ----
function rollExtremesPrior(arr, n) {
  // highest/lowest of the PRIOR n values (excludes current) -> for breakouts
  const hi = new Array(arr.length).fill(null), lo = new Array(arr.length).fill(null);
  for (let i = 0; i < arr.length; i++) {
    if (i < n) continue;
    let mx = -Infinity, mn = Infinity;
    for (let k = i - n; k < i; k++) { mx = Math.max(mx, arr[k]); mn = Math.min(mn, arr[k]); }
    hi[i] = mx; lo[i] = mn;
  }
  return { hi, lo };
}
function sessionVWAP(bars) {
  const out = new Array(bars.length).fill(null);
  let curDay = null, vNum = 0, vDen = 0;
  for (let i = 0; i < bars.length; i++) {
    const p = etParts(bars[i].t);
    if (p.k !== curDay) { curDay = p.k; vNum = 0; vDen = 0; }
    if (p.mins >= RTH_START && p.mins < RTH_END) {
      const hlc3 = (bars[i].h + bars[i].l + bars[i].c) / 3, v = bars[i].v || 0;
      vNum += hlc3 * v; vDen += v;
    }
    out[i] = vDen > 0 ? vNum / vDen : null;
  }
  return out;
}
function stochK(high, low, close, n) {
  const out = new Array(close.length).fill(null);
  for (let i = n - 1; i < close.length; i++) {
    let hh = -Infinity, ll = Infinity;
    for (let k = i - n + 1; k <= i; k++) { hh = Math.max(hh, high[k]); ll = Math.min(ll, low[k]); }
    out[i] = hh > ll ? ((close[i] - ll) / (hh - ll)) * 100 : 50;
  }
  return out;
}
function priorRthCloseByDay(bars) {
  // dayKey -> close of that day's LAST RTH bar; map gives PREVIOUS day's close per day
  const order = [], lastClose = new Map();
  for (const b of bars) { if (!isInRTH(b.t)) continue; const k = dayKeyOf(b.t); if (!lastClose.has(k)) order.push(k); lastClose.set(k, b.c); }
  const prior = new Map();
  for (let d = 1; d < order.length; d++) prior.set(order[d], lastClose.get(order[d - 1]));
  return prior;
}

// ============================ 10 NEW STRATEGIES ============================
// Each returns a sparse signal array: sig[i] = {dir, entry, stop, target} | null.
function buildAll(bars) {
  const close = bars.map((b) => b.c), high = bars.map((b) => b.h), low = bars.map((b) => b.l), open = bars.map((b) => b.o);
  const atr = I.atr(high, low, close, 14);
  const ema200 = I.ema(close, 200), ema20 = I.ema(close, 20), ema9 = I.ema(close, 9), ema21 = I.ema(close, 21);
  const sma5 = I.sma(close, 5);
  const basis = I.sma(close, 20), dev = I.stdev(close, 20);
  const upBB = basis.map((v, k) => v == null ? null : v + 2 * dev[k]);
  const loBB = basis.map((v, k) => v == null ? null : v - 2 * dev[k]);
  const bbw = upBB.map((v, k) => v == null ? null : v - loBB[k]);
  const rsi2 = I.rsi(close, 2);
  const { macdLine } = I.macd(close, 12, 26, 9);
  const vwap = sessionVWAP(bars);
  const kcUp = ema20.map((v, k) => v == null ? null : v + 2 * atr[k]);
  const kcLo = ema20.map((v, k) => v == null ? null : v - 2 * atr[k]);
  const don = rollExtremesPrior(high, 20), donL = rollExtremesPrior(low, 20);
  const stoch = stochK(high, low, close, 14);
  const xKcUp = I.crossover(close, kcUp), xKcLo = I.crossunder(close, kcLo);
  const xUpBB = I.crossover(close, upBB), xLoBB = I.crossunder(close, loBB);
  const x9o21 = I.crossover(ema9, ema21), x9u21 = I.crossunder(ema9, ema21);
  const priorClose = priorRthCloseByDay(bars);

  // squeeze = current BB width is the tightest of the prior 20 bars
  const squeeze = new Array(bars.length).fill(false);
  for (let i = 20; i < bars.length; i++) { if (bbw[i] == null) continue; let mn = Infinity; for (let k = i - 20; k < i; k++) if (bbw[k] != null) mn = Math.min(mn, bbw[k]); squeeze[i] = bbw[i] <= mn; }

  const N = bars.length;
  const mk = () => new Array(N).fill(null);
  const S = { vwapFade: mk(), vwapPull: mk(), keltner: mk(), rsi2: mk(), squeeze: mk(), macd0: mk(), ema921: mk(), donchian: mk(), gapFade: mk(), stoch: mk() };

  for (let i = 1; i < N; i++) {
    const e = close[i], a = atr[i];
    if (a == null || ema200[i] == null) continue;
    const up = e > ema200[i], dn = e < ema200[i];

    // 1) VWAP fade — fade a >=1.5 ATR stretch from VWAP, target VWAP
    if (vwap[i] != null) {
      const ext = (e - vwap[i]) / a;
      if (ext >= 1.5 && close[i] < open[i]) S.vwapFade[i] = { dir: -1, entry: e, stop: e + a, target: vwap[i] };
      else if (ext <= -1.5 && close[i] > open[i]) S.vwapFade[i] = { dir: 1, entry: e, stop: e - a, target: vwap[i] };
    }
    // 2) VWAP pullback in trend — reclaim VWAP with the trend, 2R target
    if (vwap[i] != null) {
      if (up && low[i] <= vwap[i] && e > vwap[i] && close[i] > open[i]) { const stop = vwap[i] - a; S.vwapPull[i] = { dir: 1, entry: e, stop, target: e + 2 * (e - stop) }; }
      else if (dn && high[i] >= vwap[i] && e < vwap[i] && close[i] < open[i]) { const stop = vwap[i] + a; S.vwapPull[i] = { dir: -1, entry: e, stop, target: e - 2 * (stop - e) }; }
    }
    // 3) Keltner breakout — close crosses EMA20 +/- 2ATR, with trend; stop=EMA20, 1.5R
    if (xKcUp[i] && up && ema20[i] < e) { const stop = ema20[i]; S.keltner[i] = { dir: 1, entry: e, stop, target: e + 1.5 * (e - stop) }; }
    else if (xKcLo[i] && dn && ema20[i] > e) { const stop = ema20[i]; S.keltner[i] = { dir: -1, entry: e, stop, target: e - 1.5 * (stop - e) }; }
    // 4) RSI(2) Connors reversal — extreme RSI2 snap-back in trend, target SMA5
    if (rsi2[i] != null && sma5[i] != null) {
      if (up && rsi2[i] < 5 && sma5[i] > e) S.rsi2[i] = { dir: 1, entry: e, stop: e - 1.5 * a, target: sma5[i] };
      else if (dn && rsi2[i] > 95 && sma5[i] < e) S.rsi2[i] = { dir: -1, entry: e, stop: e + 1.5 * a, target: sma5[i] };
    }
    // 5) BB squeeze breakout — tight then break the band; stop=basis, 2R
    if (basis[i] != null) {
      const recentSqueeze = squeeze[i] || squeeze[i - 1] || squeeze[i - 2] || squeeze[i - 3];
      if (recentSqueeze && xUpBB[i]) { const stop = basis[i]; S.squeeze[i] = { dir: 1, entry: e, stop, target: e + 2 * (e - stop) }; }
      else if (recentSqueeze && xLoBB[i]) { const stop = basis[i]; S.squeeze[i] = { dir: -1, entry: e, stop, target: e - 2 * (stop - e) }; }
    }
    // 6) MACD zero-line cross — momentum regime flip + trend filter; 1.5ATR stop, 2ATR tgt
    if (macdLine[i] != null && macdLine[i - 1] != null) {
      if (up && macdLine[i] > 0 && macdLine[i - 1] <= 0) S.macd0[i] = { dir: 1, entry: e, stop: e - 1.5 * a, target: e + 2 * a };
      else if (dn && macdLine[i] < 0 && macdLine[i - 1] >= 0) S.macd0[i] = { dir: -1, entry: e, stop: e + 1.5 * a, target: e - 2 * a };
    }
    // 7) EMA 9/21 cross with 200 trend filter; 1ATR stop, 2ATR tgt
    if (x9o21[i] && up) S.ema921[i] = { dir: 1, entry: e, stop: e - a, target: e + 2 * a };
    else if (x9u21[i] && dn) S.ema921[i] = { dir: -1, entry: e, stop: e + a, target: e - 2 * a };
    // 8) Donchian 20-bar breakout with trend; 1.5ATR stop, 2R tgt
    if (don.hi[i] != null && e > don.hi[i] && up) S.donchian[i] = { dir: 1, entry: e, stop: e - 1.5 * a, target: e + 3 * a };
    else if (donL.lo[i] != null && e < donL.lo[i] && dn) S.donchian[i] = { dir: -1, entry: e, stop: e + 1.5 * a, target: e - 3 * a };
    // 9) Opening gap fade — first RTH bar, fade gap vs prior RTH close
    {
      const p = etParts(bars[i].t);
      const firstRth = p.mins >= RTH_START && p.mins < RTH_START + 5 && (!isInRTH(bars[i - 1].t) || dayKeyOf(bars[i - 1].t) !== p.k);
      const pc = priorClose.get(p.k);
      if (firstRth && pc != null) {
        const gap = open[i] - pc;
        if (gap > 0.3 * a) S.gapFade[i] = { dir: -1, entry: e, stop: e + a, target: pc };
        else if (gap < -0.3 * a) S.gapFade[i] = { dir: 1, entry: e, stop: e - a, target: pc };
      }
    }
    // 10) Stochastic reversal — %K crossing out of 20/80 with trend; 1ATR stop, 2ATR tgt
    if (stoch[i] != null && stoch[i - 1] != null) {
      if (up && stoch[i - 1] <= 20 && stoch[i] > 20) S.stoch[i] = { dir: 1, entry: e, stop: e - a, target: e + 2 * a };
      else if (dn && stoch[i - 1] >= 80 && stoch[i] < 80) S.stoch[i] = { dir: -1, entry: e, stop: e + a, target: e - 2 * a };
    }
  }
  return S;
}

const NAMES = {
  vwapFade: "1. VWAP fade (mean-rev)",
  vwapPull: "2. VWAP pullback (trend)",
  keltner: "3. Keltner breakout",
  rsi2: "4. RSI(2) Connors reversal",
  squeeze: "5. BB squeeze breakout",
  macd0: "6. MACD zero-line cross",
  ema921: "7. EMA 9/21 cross",
  donchian: "8. Donchian 20 breakout",
  gapFade: "9. Opening gap fade",
  stoch: "10. Stochastic reversal",
};

(function main() {
  const bars = loadCsv(CSV_13);
  const days = new Set(bars.map((b) => dayKeyOf(b.t))).size;
  const S = buildAll(bars);
  const rows = Object.keys(NAMES).map((key) => ({ name: NAMES[key], r: runSignals(bars, S[key]) }));

  console.log(`NEW-STRATEGY LAB - 13-day chart only (${days} ET days / ${bars.length} 5m bars). Metrics per 1 MNQ ($2/pt).`);
  console.log(`RTH entries, flat by 16:00 ET, one position at a time, stop-first on ties.\n`);
  const hdr = "Strategy".padEnd(28) + "Trd".padStart(4) + "Win%".padStart(6) + "PF".padStart(6) + "Net$".padStart(8) + "MaxDD$".padStart(8) + "WrstDay$".padStart(9) + "Streak".padStart(7) + "AvgW/AvgL".padStart(12);
  console.log(hdr);
  console.log("-".repeat(hdr.length));
  const ranked = [...rows].sort((a, b) => b.r.netPts - a.r.netPts);
  for (const { name, r } of ranked) {
    const netStr = (r.netPts >= 0 ? "+$" : "-$") + f(Math.abs(r.netPts * PV_MNQ));
    console.log(
      name.padEnd(28) + String(r.n).padStart(4) + (f(r.winRate) + "%").padStart(6) +
      (r.pf === Infinity ? "inf" : f(r.pf, 2)).padStart(6) + netStr.padStart(8) +
      ("$" + f(r.ddPts * PV_MNQ)).padStart(8) + ("-$" + f(Math.abs(r.worstDayPts * PV_MNQ))).padStart(9) +
      (r.maxLossStreak + "L").padStart(7) + (f(r.avgWin, 1) + "/" + f(r.avgLoss, 1)).padStart(12)
    );
  }
  const best = ranked.filter((x) => x.r.n >= 4 && x.r.netPts > 0);
  console.log(`\nPositive w/ >=4 trades: ${best.length ? best.map((b) => b.name.replace(/^\d+\.\s*/, "")).join(", ") : "none"}`);
  console.log(`Caveat: 13 days = tiny sample. This ranks IDEAS to promote to multi-sample validation, not a verdict.`);
})();
