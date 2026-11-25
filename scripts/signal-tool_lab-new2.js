// =============================================================
//  lab-new2.js — 20 MORE new intraday strategies, 13-DAY chart, sized 5 MNQ.
//
//  Batch 2. Twenty distinct triggers, none repeating lab-new.js's 10. Same
//  fair exit model: RTH entries, flat by 16:00 ET, one position at a time,
//  stop-first on ties. Reported at 5 MNQ ($10/pt) with TopStep $50K Combine
//  survival flags (DLL $1,000 worst-day, MLL $2,000 drawdown).
//
//  Small-sample by design: 13 days = a few trades each. Idea leaderboard,
//  NOT proof. Promote winners to multi-sample validation before trusting.
//
//  DATA-ONLY / TopStep-compliant: reads a local CSV, never places an order.
//  Run:  node lab-new2.js
// =============================================================
"use strict";

const fs = require("fs");
require("./public/indicators.js");
const I = globalThis.Indicators;

const CSV_13 = "C:\\Users\\kaide\\Downloads\\CME_MINI_DL_MNQ1!, 5.csv";
const SIZE = 5;                 // 5 MNQ
const PV = 2 * SIZE;            // $10 / point
const DLL = 1000, MLL = 2000;   // $50K Combine daily-loss / trailing max-loss limits
const f = (x, d = 0) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));

// ---- bar IO + ET helpers ----
function loadCsv(p) {
  const rows = fs.readFileSync(p, "utf8").trim().split(/\r?\n/);
  const out = [];
  for (let i = 1; i < rows.length; i++) {
    const c = rows[i].split(","); const t = +c[0]; if (!t) continue;
    out.push({ t, o: +c[1], h: +c[2], l: +c[3], c: +c[4], v: +(c[5] || 0) });
  }
  out.sort((a, b) => a.t - b.t); return out;
}
function etParts(s) {
  const e = new Date(new Date(s * 1000).toLocaleString("en-US", { timeZone: "America/New_York" }));
  return { day: e.getDay(), mins: e.getHours() * 60 + e.getMinutes(), k: `${e.getFullYear()}-${e.getMonth()}-${e.getDate()}` };
}
const dayKeyOf = (s) => etParts(s).k;
const RTH_START = 570, RTH_END = 960;
function isInRTH(s) { const p = etParts(s); return p.day !== 0 && p.day !== 6 && p.mins >= RTH_START && p.mins < RTH_END; }

// ---- exit sim + runner + tally (identical fairness to batch 1) ----
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
const long = (e, stop, target) => target > e && stop < e ? { dir: 1, entry: e, stop, target } : null;
const short = (e, stop, target) => target < e && stop > e ? { dir: -1, entry: e, stop, target } : null;

// ---- shared precompute helpers ----
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
function openRange30(bars) {
  const hi = new Map(), lo = new Map();
  for (const b of bars) { const p = etParts(b.t); if (p.day === 0 || p.day === 6) continue; if (p.mins >= 570 && p.mins < 600) { const k = p.k; if (!hi.has(k)) { hi.set(k, b.h); lo.set(k, b.l); } hi.set(k, Math.max(hi.get(k), b.h)); lo.set(k, Math.min(lo.get(k), b.l)); } }
  return { hi, lo };
}
function sessionVWAPbands(bars) {
  const vwap = new Array(bars.length).fill(null), sd = new Array(bars.length).fill(null);
  let curDay = null, vNum = 0, vDen = 0, vNum2 = 0;
  for (let i = 0; i < bars.length; i++) {
    const p = etParts(bars[i].t);
    if (p.k !== curDay) { curDay = p.k; vNum = 0; vDen = 0; vNum2 = 0; }
    if (p.mins >= RTH_START && p.mins < RTH_END) { const hlc3 = (bars[i].h + bars[i].l + bars[i].c) / 3, v = bars[i].v || 0; vNum += hlc3 * v; vNum2 += hlc3 * hlc3 * v; vDen += v; }
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

// ============================ 20 NEW STRATEGIES ============================
function buildAll(bars) {
  const close = bars.map((b) => b.c), high = bars.map((b) => b.h), low = bars.map((b) => b.l), open = bars.map((b) => b.o), vol = bars.map((b) => b.v);
  const atr = I.atr(high, low, close, 14);
  const ema200 = I.ema(close, 200), ema50 = I.ema(close, 50), ema20 = I.ema(close, 20), ema9 = I.ema(close, 9), ema21 = I.ema(close, 21);
  const basis = I.sma(close, 20), dev = I.stdev(close, 20);
  const upBB = basis.map((v, k) => v == null ? null : v + 2 * dev[k]);
  const loBB = basis.map((v, k) => v == null ? null : v - 2 * dev[k]);
  const rsi14 = I.rsi(close, 14);
  const { macdLine, hist } = I.macd(close, 12, 26, 9);
  const dOpen = dayOpenArr(bars);
  const pHLC = priorRthHLC(bars), or30 = openRange30(bars);
  const { vwap, sd } = sessionVWAPbands(bars);
  const volAvg = I.sma(vol, 20);
  const cciArr = cci(high, low, close, 20), wpr = williamsR(high, low, close, 14);
  const { haC, haO } = heikin(bars);
  const don10 = rollExtremesPrior(high, 10), don10L = rollExtremesPrior(low, 10);
  const xEma200 = I.crossover(close, ema200), xEma200d = I.crossunder(close, ema200);
  const xRsi50u = I.crossover(rsi14, rsi14.map(() => 50)), xRsi50d = I.crossunder(rsi14, rsi14.map(() => 50));

  const N = bars.length, mk = () => new Array(N).fill(null);
  const KEYS = ["keltPull", "openDrive", "atrOpen", "thrust3", "insideBar", "nr7", "pivot", "pdhBreak", "pdhFade", "ema200Reclaim",
    "macdHist", "rsi50", "pctB", "williams", "cciRev", "volFade", "volBreak", "vwapBand", "haFlip", "lateDay"];
  const S = {}; for (const k of KEYS) S[k] = mk();
  const fired = { openDrive: new Set(), atrOpen: new Set() };

  for (let i = 2; i < N; i++) {
    const e = close[i], a = atr[i];
    if (a == null || ema200[i] == null) continue;
    const up = e > ema200[i], dn = e < ema200[i];
    const p = etParts(bars[i].t), dk = p.k;
    const ph = pHLC.get(dk);

    // 1) Keltner pullback (trend): uptrend, dip to EMA20, reclaim -> long; stop EMA20-1ATR, 2R
    if (ema20[i] != null) {
      if (up && low[i] <= ema20[i] && e > ema20[i] && close[i] > open[i]) { const stop = ema20[i] - a; S.keltPull[i] = long(e, stop, e + 2 * (e - stop)); }
      else if (dn && high[i] >= ema20[i] && e < ema20[i] && close[i] < open[i]) { const stop = ema20[i] + a; S.keltPull[i] = short(e, stop, e - 2 * (stop - e)); }
    }
    // 2) Opening drive continuation: first close beyond 09:30-10:00 range, with trend; stop other side, 1.5R
    if (p.mins >= 600 && or30.hi.has(dk) && !fired.openDrive.has(dk)) {
      const rh = or30.hi.get(dk), rl = or30.lo.get(dk);
      if (e > rh && up) { fired.openDrive.add(dk); S.openDrive[i] = long(e, rl, e + 1.5 * (e - rl)); }
      else if (e < rl && dn) { fired.openDrive.add(dk); S.openDrive[i] = short(e, rh, e - 1.5 * (rh - e)); }
    }
    // 3) ATR-from-open breakout: first time price is >=1.5 ATR from the day open, with trend; 1.5ATR stop, 2ATR
    if (dOpen[i] != null && !fired.atrOpen.has(dk)) {
      if (e >= dOpen[i] + 1.5 * a && up) { fired.atrOpen.add(dk); S.atrOpen[i] = long(e, e - 1.5 * a, e + 2 * a); }
      else if (e <= dOpen[i] - 1.5 * a && dn) { fired.atrOpen.add(dk); S.atrOpen[i] = short(e, e + 1.5 * a, e - 2 * a); }
    }
    // 4) 3-bar thrust continuation: 3 rising/falling closes + trend; 1.5ATR stop, 2ATR
    if (up && close[i] > close[i - 1] && close[i - 1] > close[i - 2] && close[i - 2] > close[i - 3]) S.thrust3[i] = long(e, e - 1.5 * a, e + 2 * a);
    else if (dn && close[i] < close[i - 1] && close[i - 1] < close[i - 2] && close[i - 2] < close[i - 3]) S.thrust3[i] = short(e, e + 1.5 * a, e - 2 * a);
    // 5) Inside-bar breakout: bar i-1 inside i-2, break of i-1 range with trend; stop other side, 2R
    if (high[i - 1] <= high[i - 2] && low[i - 1] >= low[i - 2]) {
      if (up && high[i] > high[i - 1]) { const stop = low[i - 1]; S.insideBar[i] = long(e, stop, e + 2 * (e - stop)); }
      else if (dn && low[i] < low[i - 1]) { const stop = high[i - 1]; S.insideBar[i] = short(e, stop, e - 2 * (stop - e)); }
    }
    // 6) NR7 breakout: bar i-1 is narrowest range of last 7, break it with trend; 1.5ATR stop, 2ATR
    {
      let isNR7 = i >= 8; const r1 = high[i - 1] - low[i - 1];
      for (let k = 2; k <= 7 && isNR7; k++) if (high[i - k] - low[i - k] < r1) isNR7 = false;
      if (isNR7 && up && high[i] > high[i - 1]) S.nr7[i] = long(e, e - 1.5 * a, e + 2 * a);
      else if (isNR7 && dn && low[i] < low[i - 1]) S.nr7[i] = short(e, e + 1.5 * a, e - 2 * a);
    }
    // 7) Pivot bounce: floor pivot P from prior RTH HLC; reclaim P with trend -> target R1/S1
    if (ph) {
      const P = (ph.h + ph.l + ph.c) / 3, R1 = 2 * P - ph.l, S1 = 2 * P - ph.h;
      if (up && low[i] <= P && e > P) S.pivot[i] = long(e, P - a, R1);
      else if (dn && high[i] >= P && e < P) S.pivot[i] = short(e, P + a, S1);
    }
    // 8) Prior-day H/L breakout with trend; 1.5ATR stop, 2ATR
    if (ph) {
      if (up && close[i - 1] <= ph.h && e > ph.h) S.pdhBreak[i] = long(e, e - 1.5 * a, e + 2 * a);
      else if (dn && close[i - 1] >= ph.l && e < ph.l) S.pdhBreak[i] = short(e, e + 1.5 * a, e - 2 * a);
    }
    // 9) Prior-day H/L fade: rejection at PDH/PDL -> fade toward VWAP; 1ATR stop
    if (ph && vwap[i] != null) {
      if (high[i] >= ph.h && e < ph.h && e > vwap[i]) S.pdhFade[i] = short(e, e + a, vwap[i]);
      else if (low[i] <= ph.l && e > ph.l && e < vwap[i]) S.pdhFade[i] = long(e, e - a, vwap[i]);
    }
    // 10) EMA200 reclaim (regime change); 1.5ATR stop, 2.5ATR
    if (xEma200[i]) S.ema200Reclaim[i] = long(e, e - 1.5 * a, e + 2.5 * a);
    else if (xEma200d[i]) S.ema200Reclaim[i] = short(e, e + 1.5 * a, e - 2.5 * a);
    // 11) MACD histogram zero-cross + trend; 1.5ATR stop, 2ATR
    if (hist[i] != null && hist[i - 1] != null) {
      if (up && hist[i] > 0 && hist[i - 1] <= 0) S.macdHist[i] = long(e, e - 1.5 * a, e + 2 * a);
      else if (dn && hist[i] < 0 && hist[i - 1] >= 0) S.macdHist[i] = short(e, e + 1.5 * a, e - 2 * a);
    }
    // 12) RSI(14) 50-cross + trend; 1ATR stop, 2ATR
    if (up && xRsi50u[i]) S.rsi50[i] = long(e, e - a, e + 2 * a);
    else if (dn && xRsi50d[i]) S.rsi50[i] = short(e, e + a, e - 2 * a);
    // 13) Bollinger %B reversion: poke below lower band then close back inside -> target basis; 1ATR stop
    if (basis[i] != null && loBB[i] != null) {
      if (low[i] < loBB[i] && e > loBB[i] && basis[i] > e) S.pctB[i] = long(e, e - a, basis[i]);
      else if (high[i] > upBB[i] && e < upBB[i] && basis[i] < e) S.pctB[i] = short(e, e + a, basis[i]);
    }
    // 14) Williams %R reversal out of -80 / -20 with trend; 1ATR stop, 2ATR
    if (wpr[i] != null && wpr[i - 1] != null) {
      if (up && wpr[i - 1] <= -80 && wpr[i] > -80) S.williams[i] = long(e, e - a, e + 2 * a);
      else if (dn && wpr[i - 1] >= -20 && wpr[i] < -20) S.williams[i] = short(e, e + a, e - 2 * a);
    }
    // 15) CCI extreme reversal: cross back through +/-100 with trend -> target SMA20; 1.5ATR stop
    if (cciArr[i] != null && cciArr[i - 1] != null && basis[i] != null) {
      if (up && cciArr[i - 1] <= -100 && cciArr[i] > -100 && basis[i] > e) S.cciRev[i] = long(e, e - 1.5 * a, basis[i]);
      else if (dn && cciArr[i - 1] >= 100 && cciArr[i] < 100 && basis[i] < e) S.cciRev[i] = short(e, e + 1.5 * a, basis[i]);
    }
    // 16) Volume-spike exhaustion fade: vol>2x avg + wide bar -> fade toward VWAP; 1ATR stop
    if (volAvg[i] != null && vol[i] > 2 * volAvg[i] && (high[i] - low[i]) > 1.5 * a && vwap[i] != null) {
      if (close[i] > open[i] && e > vwap[i]) S.volFade[i] = short(e, e + a, vwap[i]);
      else if (close[i] < open[i] && e < vwap[i]) S.volFade[i] = long(e, e - a, vwap[i]);
    }
    // 17) Volume-confirmed breakout: break of 10-bar high/low on >1.5x vol + trend; 1.5ATR stop, 3ATR
    if (don10.hi[i] != null && volAvg[i] != null && vol[i] > 1.5 * volAvg[i]) {
      if (up && e > don10.hi[i]) S.volBreak[i] = long(e, e - 1.5 * a, e + 3 * a);
      else if (dn && e < don10L.lo[i]) S.volBreak[i] = short(e, e + 1.5 * a, e - 3 * a);
    }
    // 18) VWAP 2-sigma band reversion: poke beyond band, close back inside -> target VWAP; 1ATR stop
    if (vwap[i] != null && sd[i] != null && sd[i] > 0) {
      const ub = vwap[i] + 2 * sd[i], lb = vwap[i] - 2 * sd[i];
      if (low[i] < lb && e > lb && e < vwap[i]) S.vwapBand[i] = long(e, e - a, vwap[i]);
      else if (high[i] > ub && e < ub && e > vwap[i]) S.vwapBand[i] = short(e, e + a, vwap[i]);
    }
    // 19) Heikin-Ashi flip continuation: HA color flips with trend; 1.5ATR stop, 2ATR
    {
      const upNow = haC[i] > haO[i], upPrev = haC[i - 1] > haO[i - 1];
      if (up && upNow && !upPrev) S.haFlip[i] = long(e, e - 1.5 * a, e + 2 * a);
      else if (dn && !upNow && upPrev) S.haFlip[i] = short(e, e + 1.5 * a, e - 2 * a);
    }
    // 20) Late-day momentum (14:00-15:30 ET): trade day direction on EMA9/21 alignment; 1ATR stop, 2ATR
    if (p.mins >= 840 && p.mins <= 930 && dOpen[i] != null && ema9[i] != null && ema21[i] != null) {
      const dayUp = e > dOpen[i];
      if (up && dayUp && ema9[i] > ema21[i] && close[i] > open[i]) S.lateDay[i] = long(e, e - a, e + 2 * a);
      else if (dn && !dayUp && ema9[i] < ema21[i] && close[i] < open[i]) S.lateDay[i] = short(e, e + a, e - 2 * a);
    }
  }
  return { S, KEYS };
}

const NAMES = {
  keltPull: "1. Keltner pullback (trend)", openDrive: "2. Opening drive continuation", atrOpen: "3. ATR-from-open breakout",
  thrust3: "4. 3-bar thrust continuation", insideBar: "5. Inside-bar breakout", nr7: "6. NR7 breakout",
  pivot: "7. Floor-pivot bounce", pdhBreak: "8. Prior-day H/L breakout", pdhFade: "9. Prior-day H/L fade",
  ema200Reclaim: "10. EMA200 reclaim", macdHist: "11. MACD histogram cross", rsi50: "12. RSI(14) 50-cross",
  pctB: "13. Bollinger %B reversion", williams: "14. Williams %R reversal", cciRev: "15. CCI extreme reversal",
  volFade: "16. Volume-spike fade", volBreak: "17. Volume-confirmed breakout", vwapBand: "18. VWAP 2sigma reversion",
  haFlip: "19. Heikin-Ashi flip", lateDay: "20. Late-day momentum",
};

function main() {
  const bars = loadCsv(CSV_13);
  const days = new Set(bars.map((b) => dayKeyOf(b.t))).size;
  const { S, KEYS } = buildAll(bars);
  const rows = KEYS.map((key) => ({ name: NAMES[key], r: runSignals(bars, S[key]) }));

  console.log(`NEW-STRATEGY LAB (batch 2) - 13-day chart only (${days} ET days / ${bars.length} 5m bars). Sized ${SIZE} MNQ ($${PV}/pt).`);
  console.log(`RTH entries, flat by 16:00 ET, one position at a time, stop-first on ties. Combine: DLL $${DLL}/day, MLL $${MLL}.\n`);
  const hdr = "Strategy".padEnd(30) + "Trd".padStart(4) + "Win%".padStart(6) + "PF".padStart(6) + "Net$".padStart(9) + "MaxDD$".padStart(8) + "WrstDay$".padStart(10) + "Strk".padStart(6) + "Combine".padStart(9);
  console.log(hdr); console.log("-".repeat(hdr.length));
  const ranked = [...rows].sort((a, b) => b.r.netPts - a.r.netPts);
  for (const { name, r } of ranked) {
    const net = r.netPts * PV, dd = r.ddPts * PV, wd = Math.abs(r.worstDayPts * PV);
    const survive = wd < DLL && dd < MLL ? "OK" : (wd >= DLL ? "DLL!" : "MLL!");
    console.log(
      name.padEnd(30) + String(r.n).padStart(4) + (f(r.winRate) + "%").padStart(6) +
      (r.pf === Infinity ? "inf" : f(r.pf, 2)).padStart(6) +
      ((net >= 0 ? "+$" : "-$") + f(Math.abs(net))).padStart(9) +
      ("$" + f(dd)).padStart(8) + ("-$" + f(wd)).padStart(10) +
      (r.maxLossStreak + "L").padStart(6) + survive.padStart(9)
    );
  }
  const good = ranked.filter((x) => x.r.n >= 4 && x.r.netPts > 0 && Math.abs(x.r.worstDayPts * PV) < DLL && x.r.ddPts * PV < MLL);
  console.log(`\nPositive + Combine-survivable (>=4 trades): ${good.length ? good.map((b) => b.name.replace(/^\d+\.\s*/, "")).join(", ") : "none"}`);
  console.log(`Caveat: 13 days = tiny sample. Ranks IDEAS to promote to multi-sample validation, not a verdict.`);
}

if (require.main === module) main();

// Reusable by validation harnesses (e.g. validate58.js).
module.exports = { loadCsv, buildAll, runSignals, tally, dayKeyOf, isInRTH, NAMES, SIZE, PV, DLL, MLL };
