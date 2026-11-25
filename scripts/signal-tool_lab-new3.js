// =============================================================
//  lab-new3.js — batch 3: 20 MORE new strategies on the 13-DAY chart, with the
//  $50K TopStep Combine rules ENFORCED inside the simulation (not just flagged).
//
//  Enforcement (so results reflect RULE-LEGAL trading):
//    - Daily-loss lockout : stop new entries once realized day P&L <= -$700.
//    - Per-trade risk cap  : skip any signal whose stop risks > $300 (~30pt @5MNQ).
//        => worst possible day = -700 lockout + one -300 stop = -999 < $1,000 DLL.
//    - Trailing MLL kill   : account FAILS if equity gives back $2,000 from peak.
//    - Profit target       : flag when running equity first reaches +$3,000.
//    - Contracts           : 5 MNQ (within the 5-contract cap).
//
//  20 distinct triggers, none repeating batch 1 (lab-new.js) or batch 2
//  (lab-new2.js). Same fair exit model: RTH entries, flat by 16:00 ET, one
//  position at a time, stop-first on ties.
//
//  Small-sample by design: 13 days = a few trades each. Idea leaderboard, NOT
//  proof. Promote winners to multi-sample validation (validate58.js).
//
//  DATA-ONLY / TopStep-compliant: reads a local CSV, never places an order.
//  Run:  node lab-new3.js
// =============================================================
"use strict";

const fs = require("fs");
require("./public/indicators.js");
const I = globalThis.Indicators;

const CSV_13 = "C:\\Users\\kaide\\Downloads\\CME_MINI_DL_MNQ1!, 5.csv";
const SIZE = 5, PV = 2 * SIZE;          // 5 MNQ -> $10/pt
const DLL = 1000, MLL = 2000, TARGET = 3000;
const DAILY_STOP = 700, MAX_TRADE_RISK = 300; // enforcement knobs (see header)
const f = (x, d = 0) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));

// ---- bar IO + ET helpers ----
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

// ---- exit sim ----
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

// ---- EVAL-ENFORCED runner: applies lockout, per-trade cap, MLL kill, target ----
function runEval(bars, sig) {
  const trades = []; let i = 1, curDay = null, dayPnL = 0, locked = false;
  let cum = 0, peak = 0, failed = false, passedAt = null, skipped = 0; const lockoutDays = new Set();
  while (i < bars.length) {
    if (!(sig[i] && isInRTH(bars[i].t))) { i++; continue; }
    const dk = dayKeyOf(bars[i].t);
    if (dk !== curDay) { curDay = dk; dayPnL = 0; locked = false; }
    if (failed) break;
    if (locked) { i++; continue; }
    const s = sig[i];
    if (Math.abs(s.entry - s.stop) * PV > MAX_TRADE_RISK) { skipped++; i++; continue; }
    const r = simulateTrade(bars, i, s);
    const pnl = r.pts * PV;
    dayPnL += pnl; cum += pnl; peak = Math.max(peak, cum);
    trades.push({ date: dk, pts: r.pts });
    if (passedAt == null && cum >= TARGET) passedAt = trades.length;
    if (cum <= Math.min(0, peak - MLL)) failed = true;
    if (dayPnL <= -DAILY_STOP) { locked = true; lockoutDays.add(dk); }
    i = r.exitIdx + 1;
  }
  const t = tally(trades);
  t.skipped = skipped; t.failed = failed; t.passedAt = passedAt; t.lockoutDays = lockoutDays.size; t.cum = cum;
  return t;
}
function tally(trades) {
  const wins = trades.filter((t) => t.pts > 0);
  const gW = wins.reduce((s, t) => s + t.pts, 0);
  const gL = Math.abs(trades.filter((t) => t.pts <= 0).reduce((s, t) => s + t.pts, 0));
  const netPts = trades.reduce((s, t) => s + t.pts, 0);
  let peak = 0, cum = 0, maxDD = 0;
  for (const t of trades) { cum += t.pts; peak = Math.max(peak, cum); maxDD = Math.max(maxDD, peak - cum); }
  const byDay = new Map();
  for (const t of trades) byDay.set(t.date, (byDay.get(t.date) || 0) + t.pts);
  const worstDayPts = trades.length ? Math.min(0, ...byDay.values()) : 0;
  return { n: trades.length, winRate: trades.length ? (wins.length / trades.length) * 100 : 0, pf: gL > 0 ? gW / gL : (gW > 0 ? Infinity : 0), netPts, ddPts: maxDD, worstDayPts };
}
const long = (e, stop, target) => target > e && stop < e ? { dir: 1, entry: e, stop, target } : null;
const short = (e, stop, target) => target < e && stop > e ? { dir: -1, entry: e, stop, target } : null;

// ---- precompute helpers ----
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
function firstBarRange(bars) { // dayKey -> {h,l} of the 09:30 5-min bar
  const hi = new Map(), lo = new Map();
  for (const b of bars) { const p = etParts(b.t); if (p.day === 0 || p.day === 6) continue; if (p.mins >= 570 && p.mins < 575) { hi.set(p.k, b.h); lo.set(p.k, b.l); } }
  return { hi, lo };
}
function priorRthHLC(bars) {
  const order = [], hi = new Map(), lo = new Map(), cl = new Map();
  for (const b of bars) { if (!isInRTH(b.t)) continue; const k = dayKeyOf(b.t); if (!hi.has(k)) { order.push(k); hi.set(k, b.h); lo.set(k, b.l); } hi.set(k, Math.max(hi.get(k), b.h)); lo.set(k, Math.min(lo.get(k), b.l)); cl.set(k, b.c); }
  const prior = new Map();
  for (let d = 1; d < order.length; d++) prior.set(order[d], { h: hi.get(order[d - 1]), l: lo.get(order[d - 1]), c: cl.get(order[d - 1]) });
  return prior;
}
function sessionVWAP(bars) {
  const out = new Array(bars.length).fill(null);
  let curDay = null, vNum = 0, vDen = 0;
  for (let i = 0; i < bars.length; i++) { const p = etParts(bars[i].t); if (p.k !== curDay) { curDay = p.k; vNum = 0; vDen = 0; } if (p.mins >= RTH_START && p.mins < RTH_END) { const hlc3 = (bars[i].h + bars[i].l + bars[i].c) / 3, v = bars[i].v || 0; vNum += hlc3 * v; vDen += v; } out[i] = vDen > 0 ? vNum / vDen : null; }
  return out;
}
function roc(close, n) { return close.map((c, i) => (i < n || close[i - n] === 0) ? null : (c - close[i - n]) / close[i - n] * 100); }
function stochKD(high, low, close, n) {
  const K = new Array(close.length).fill(null);
  for (let i = n - 1; i < close.length; i++) { let hh = -Infinity, ll = Infinity; for (let k = i - n + 1; k <= i; k++) { hh = Math.max(hh, high[k]); ll = Math.min(ll, low[k]); } K[i] = hh > ll ? (close[i] - ll) / (hh - ll) * 100 : 50; }
  const D = I.sma(K.map((v) => v == null ? 0 : v), 3).map((v, i) => K[i] == null ? null : v);
  return { K, D };
}
function supertrend(high, low, close, atr, mult) {
  const n = close.length, dir = new Array(n).fill(0);
  let upPrev = null, loPrev = null, stPrev = null;
  for (let i = 0; i < n; i++) {
    if (atr[i] == null) { dir[i] = 0; continue; }
    const hl2 = (high[i] + low[i]) / 2; let up = hl2 + mult * atr[i], lo = hl2 - mult * atr[i];
    if (upPrev != null) { up = (up < upPrev || close[i - 1] > upPrev) ? up : upPrev; lo = (lo > loPrev || close[i - 1] < loPrev) ? lo : loPrev; }
    let d; if (stPrev == null) d = 1; else if (stPrev === upPrev) d = close[i] > up ? 1 : -1; else d = close[i] < lo ? -1 : 1;
    dir[i] = d; stPrev = d === 1 ? lo : up; upPrev = up; loPrev = lo;
  }
  return dir;
}
function lastSwing(arr, isHigh, left, right) {
  const n = arr.length, out = new Array(n).fill(null); let last = null;
  for (let i = 0; i < n; i++) { const c = i - right; if (c >= left) { let piv = true; for (let k = 1; k <= left && piv; k++) if (isHigh ? arr[c - k] > arr[c] : arr[c - k] < arr[c]) piv = false; for (let k = 1; k <= right && piv; k++) if (isHigh ? arr[c + k] > arr[c] : arr[c + k] < arr[c]) piv = false; if (piv) last = arr[c]; } out[i] = last; }
  return out;
}

// ============================ 20 NEW STRATEGIES (batch 3) ============================
function buildAll(bars) {
  const close = bars.map((b) => b.c), high = bars.map((b) => b.h), low = bars.map((b) => b.l), open = bars.map((b) => b.o), vol = bars.map((b) => b.v);
  const atr = I.atr(high, low, close, 14), atr5 = I.atr(high, low, close, 5);
  const ema200 = I.ema(close, 200), ema50 = I.ema(close, 50), ema21 = I.ema(close, 21), ema13 = I.ema(close, 13), ema8 = I.ema(close, 8);
  const basis = I.sma(close, 20), dev = I.stdev(close, 20);
  const upBB = basis.map((v, k) => v == null ? null : v + 2 * dev[k]), loBB = basis.map((v, k) => v == null ? null : v - 2 * dev[k]);
  const { macdLine, signalLine } = I.macd(close, 12, 26, 9);
  const vwap = sessionVWAP(bars);
  const rocArr = roc(close, 10);
  const st = supertrend(high, low, close, atr, 3);
  const { K, D } = stochKD(high, low, close, 14);
  const swHi = lastSwing(high, true, 3, 3), swLo = lastSwing(low, false, 3, 3);
  const dOpen = dayOpenArr(bars), fbr = firstBarRange(bars), pHLC = priorRthHLC(bars);
  const d20 = rollExtremesPrior(high, 20), d20L = rollExtremesPrior(low, 20), d5 = rollExtremesPrior(high, 5), d5L = rollExtremesPrior(low, 5);
  const volAvg = I.sma(vol, 20);
  const xVwap = I.crossover(close, vwap), xVwapD = I.crossunder(close, vwap);
  const xMacdSig = I.crossover(macdLine, signalLine), xMacdSigD = I.crossunder(macdLine, signalLine);
  const xKD = I.crossover(K, D), xKDd = I.crossunder(K, D);

  const N = bars.length, mk = () => new Array(N).fill(null);
  const KEYS = ["outsideRev", "keyRev", "tripleEma", "supertrend", "rocMom", "ema50bounce", "vwapReclaim", "firstBarBreak", "lastHourFade", "pullbackCount",
    "donMid", "macdSig", "bandWalk", "atrContract", "pivotBreak", "gapGo", "openRev", "stochCross", "closeStrength", "swingBreak"];
  const S = {}; for (const k of KEYS) S[k] = mk();
  const fired = { firstBarBreak: new Set(), gapGo: new Set() };

  for (let i = 3; i < N; i++) {
    const e = close[i], a = atr[i];
    if (a == null || ema200[i] == null) continue;
    const up = e > ema200[i], dn = e < ema200[i];
    const p = etParts(bars[i].t), dk = p.k, ph = pHLC.get(dk);

    // 1) Outside-bar reversal in trend: bar engulfs prior, buy the dip in uptrend
    if (high[i] > high[i - 1] && low[i] < low[i - 1]) {
      if (up && close[i] > open[i]) S.outsideRev[i] = long(e, low[i], e + 1.5 * (e - low[i]));
      else if (dn && close[i] < open[i]) S.outsideRev[i] = short(e, high[i], e - 1.5 * (high[i] - e));
    }
    // 2) Key reversal bar: new 5-bar low but closes up & above prior close (trend resume)
    {
      let nl = true, nh = true; for (let k = 1; k <= 5; k++) { if (low[i] >= low[i - k]) nl = false; if (high[i] <= high[i - k]) nh = false; }
      if (up && nl && close[i] > open[i] && close[i] > close[i - 1]) S.keyRev[i] = long(e, low[i], e + 2 * (e - low[i]));
      else if (dn && nh && close[i] < open[i] && close[i] < close[i - 1]) S.keyRev[i] = short(e, high[i], e - 2 * (high[i] - e));
    }
    // 3) Triple-EMA stack (8>13>21) pullback to EMA13, reclaim
    if (ema8[i] != null && ema13[i] != null && ema21[i] != null) {
      if (ema8[i] > ema13[i] && ema13[i] > ema21[i] && low[i] <= ema13[i] && e > ema13[i]) S.tripleEma[i] = long(e, ema21[i], e + 2 * (e - ema21[i]));
      else if (ema8[i] < ema13[i] && ema13[i] < ema21[i] && high[i] >= ema13[i] && e < ema13[i]) S.tripleEma[i] = short(e, ema21[i], e - 2 * (ema21[i] - e));
    }
    // 4) Supertrend flip with trend; 1.5ATR stop, 2.5ATR
    if (st[i] === 1 && st[i - 1] === -1 && up) S.supertrend[i] = long(e, e - 1.5 * a, e + 2.5 * a);
    else if (st[i] === -1 && st[i - 1] === 1 && dn) S.supertrend[i] = short(e, e + 1.5 * a, e - 2.5 * a);
    // 5) ROC momentum: ROC(10) crosses +/-0.3% with trend; 1.5ATR stop, 2ATR
    if (rocArr[i] != null && rocArr[i - 1] != null) {
      if (up && rocArr[i - 1] <= 0.3 && rocArr[i] > 0.3) S.rocMom[i] = long(e, e - 1.5 * a, e + 2 * a);
      else if (dn && rocArr[i - 1] >= -0.3 && rocArr[i] < -0.3) S.rocMom[i] = short(e, e + 1.5 * a, e - 2 * a);
    }
    // 6) EMA50 bounce in trend
    if (ema50[i] != null) {
      if (up && low[i] <= ema50[i] && e > ema50[i] && close[i] > open[i]) S.ema50bounce[i] = long(e, ema50[i] - a, e + 2 * (e - (ema50[i] - a)));
      else if (dn && high[i] >= ema50[i] && e < ema50[i] && close[i] < open[i]) S.ema50bounce[i] = short(e, ema50[i] + a, e - 2 * ((ema50[i] + a) - e));
    }
    // 7) VWAP reclaim momentum: close crosses VWAP with trend; 1ATR stop, 2ATR
    if (up && xVwap[i]) S.vwapReclaim[i] = long(e, e - a, e + 2 * a);
    else if (dn && xVwapD[i]) S.vwapReclaim[i] = short(e, e + a, e - 2 * a);
    // 8) First 5-min bar (09:30) breakout, once/day, with trend; stop other side, 1.5R
    if (p.mins > 575 && fbr.hi.has(dk) && !fired.firstBarBreak.has(dk)) {
      const rh = fbr.hi.get(dk), rl = fbr.lo.get(dk);
      if (up && e > rh) { fired.firstBarBreak.add(dk); S.firstBarBreak[i] = long(e, rl, e + 1.5 * (e - rl)); }
      else if (dn && e < rl) { fired.firstBarBreak.add(dk); S.firstBarBreak[i] = short(e, rh, e - 1.5 * (rh - e)); }
    }
    // 9) Last-hour fade (15:00-15:45): fade >=1ATR extension from VWAP back to VWAP
    if (p.mins >= 900 && p.mins <= 945 && vwap[i] != null) {
      const ext = (e - vwap[i]) / a;
      if (ext >= 1 && close[i] < open[i]) S.lastHourFade[i] = short(e, e + a, vwap[i]);
      else if (ext <= -1 && close[i] > open[i]) S.lastHourFade[i] = long(e, e - a, vwap[i]);
    }
    // 10) Pullback count: 3 counter closes in trend then a with-trend bar; 1ATR stop, 2ATR
    if (up && close[i - 1] < close[i - 2] && close[i - 2] < close[i - 3] && close[i] > close[i - 1]) S.pullbackCount[i] = long(e, e - a, e + 2 * a);
    else if (dn && close[i - 1] > close[i - 2] && close[i - 2] > close[i - 3] && close[i] < close[i - 1]) S.pullbackCount[i] = short(e, e + a, e - 2 * a);
    // 11) Donchian-20 midline bounce in trend
    if (d20.hi[i] != null) {
      const mid = (d20.hi[i] + d20L.lo[i]) / 2;
      if (up && low[i] <= mid && e > mid) S.donMid[i] = long(e, mid - a, e + 2 * (e - (mid - a)));
      else if (dn && high[i] >= mid && e < mid) S.donMid[i] = short(e, mid + a, e - 2 * ((mid + a) - e));
    }
    // 12) MACD signal-line cross with trend; 1.5ATR stop, 2ATR
    if (up && xMacdSig[i]) S.macdSig[i] = long(e, e - 1.5 * a, e + 2 * a);
    else if (dn && xMacdSigD[i]) S.macdSig[i] = short(e, e + 1.5 * a, e - 2 * a);
    // 13) Band-walk continuation: 2 closes beyond the band with trend; 1.5ATR stop, 2ATR
    if (upBB[i] != null && upBB[i - 1] != null) {
      if (up && close[i] > upBB[i] && close[i - 1] > upBB[i - 1]) S.bandWalk[i] = long(e, e - 1.5 * a, e + 2 * a);
      else if (dn && close[i] < loBB[i] && close[i - 1] < loBB[i - 1]) S.bandWalk[i] = short(e, e + 1.5 * a, e - 2 * a);
    }
    // 14) ATR-contraction breakout: ATR5 < 0.8*ATR14, then break 5-bar high/low with trend
    if (atr5[i] != null && atr5[i] < 0.8 * a && d5.hi[i] != null) {
      if (up && e > d5.hi[i]) S.atrContract[i] = long(e, e - 1.5 * a, e + 2.5 * a);
      else if (dn && e < d5L.lo[i]) S.atrContract[i] = short(e, e + 1.5 * a, e - 2.5 * a);
    }
    // 15) Pivot R1/S1 breakout (momentum beyond first pivot levels)
    if (ph) {
      const P = (ph.h + ph.l + ph.c) / 3, R1 = 2 * P - ph.l, S1 = 2 * P - ph.h;
      if (up && close[i - 1] <= R1 && e > R1) S.pivotBreak[i] = long(e, e - 1.5 * a, e + 2 * a);
      else if (dn && close[i - 1] >= S1 && e < S1) S.pivotBreak[i] = short(e, e + 1.5 * a, e - 2 * a);
    }
    // 16) Gap-and-go continuation: first RTH bar gaps >0.3ATR and closes in gap direction
    {
      const firstRth = p.mins >= RTH_START && p.mins < RTH_START + 5 && (!isInRTH(bars[i - 1].t) || dayKeyOf(bars[i - 1].t) !== dk);
      const pc = ph ? ph.c : null;
      if (firstRth && pc != null && !fired.gapGo.has(dk)) {
        const gap = open[i] - pc;
        if (gap > 0.3 * a && close[i] > open[i]) { fired.gapGo.add(dk); S.gapGo[i] = long(e, low[i], e + 2 * (e - low[i])); }
        else if (gap < -0.3 * a && close[i] < open[i]) { fired.gapGo.add(dk); S.gapGo[i] = short(e, high[i], e - 2 * (high[i] - e)); }
      }
    }
    // 17) Opening reversal (09:45-10:15): fade >=1.2ATR move off the open back to open
    if (p.mins >= 585 && p.mins <= 615 && dOpen[i] != null) {
      const move = (e - dOpen[i]) / a;
      if (move >= 1.2 && close[i] < open[i]) S.openRev[i] = short(e, e + a, dOpen[i]);
      else if (move <= -1.2 && close[i] > open[i]) S.openRev[i] = long(e, e - a, dOpen[i]);
    }
    // 18) Stochastic %K/%D cross in zones with trend; 1ATR stop, 2ATR
    if (K[i] != null && D[i] != null) {
      if (up && xKD[i] && K[i] < 40) S.stochCross[i] = long(e, e - a, e + 2 * a);
      else if (dn && xKDd[i] && K[i] > 60) S.stochCross[i] = short(e, e + a, e - 2 * a);
    }
    // 19) Close-strength momentum: close in top/bottom 15% of a wide bar, with trend
    {
      const rng = high[i] - low[i];
      if (rng > 0.8 * a) {
        if (up && close[i] >= high[i] - 0.15 * rng) S.closeStrength[i] = long(e, e - a, e + 2 * a);
        else if (dn && close[i] <= low[i] + 0.15 * rng) S.closeStrength[i] = short(e, e + a, e - 2 * a);
      }
    }
    // 20) Swing-structure breakout: break of last confirmed swing high/low with trend
    if (swHi[i] != null && swLo[i] != null) {
      if (up && close[i - 1] <= swHi[i] && e > swHi[i]) S.swingBreak[i] = long(e, e - 1.5 * a, e + 2 * a);
      else if (dn && close[i - 1] >= swLo[i] && e < swLo[i]) S.swingBreak[i] = short(e, e + 1.5 * a, e - 2 * a);
    }
  }
  return { S, KEYS };
}

const NAMES = {
  outsideRev: "1. Outside-bar reversal", keyRev: "2. Key reversal bar", tripleEma: "3. Triple-EMA stack pullback",
  supertrend: "4. Supertrend flip", rocMom: "5. ROC momentum", ema50bounce: "6. EMA50 bounce",
  vwapReclaim: "7. VWAP reclaim momentum", firstBarBreak: "8. First-5min-bar breakout", lastHourFade: "9. Last-hour fade",
  pullbackCount: "10. Pullback-count entry", donMid: "11. Donchian midline bounce", macdSig: "12. MACD signal-line cross",
  bandWalk: "13. Bollinger band-walk", atrContract: "14. ATR-contraction breakout", pivotBreak: "15. Pivot R1/S1 breakout",
  gapGo: "16. Gap-and-go continuation", openRev: "17. Opening reversal", stochCross: "18. Stochastic K/D cross",
  closeStrength: "19. Close-strength momentum", swingBreak: "20. Swing-structure breakout",
};

(function main() {
  const bars = loadCsv(CSV_13);
  const days = new Set(bars.map((b) => dayKeyOf(b.t))).size;
  const { S, KEYS } = buildAll(bars);
  const rows = KEYS.map((key) => ({ name: NAMES[key], r: runEval(bars, S[key]) }));

  console.log(`NEW-STRATEGY LAB (batch 3) - 13-day chart, EVAL RULES ENFORCED. ${days} ET days / ${bars.length} bars. ${SIZE} MNQ ($${PV}/pt).`);
  console.log(`Lockout day<=-$${DAILY_STOP} | per-trade cap $${MAX_TRADE_RISK} | MLL kill $${MLL} | target +$${TARGET}. Worst legal day approx -$${DAILY_STOP + MAX_TRADE_RISK}.\n`);
  const hdr = "Strategy".padEnd(30) + "Trd".padStart(4) + "Skp".padStart(4) + "Lck".padStart(4) + "Win%".padStart(6) + "PF".padStart(6) + "Net$".padStart(9) + "WrstDay$".padStart(10) + "Outcome".padStart(12);
  console.log(hdr); console.log("-".repeat(hdr.length));
  const ranked = [...rows].sort((a, b) => b.r.netPts - a.r.netPts);
  for (const { name, r } of ranked) {
    const net = r.netPts * PV, wd = Math.abs(r.worstDayPts * PV);
    const outcome = r.failed ? "FAIL-MLL" : (r.passedAt ? `PASS@${r.passedAt}` : (net > 0 ? "open +" : "open -"));
    console.log(
      name.padEnd(30) + String(r.n).padStart(4) + String(r.skipped).padStart(4) + String(r.lockoutDays).padStart(4) +
      (f(r.winRate) + "%").padStart(6) + (r.pf === Infinity ? "inf" : f(r.pf, 2)).padStart(6) +
      ((net >= 0 ? "+$" : "-$") + f(Math.abs(net))).padStart(9) + ("-$" + f(wd)).padStart(10) + outcome.padStart(12)
    );
  }
  const passed = ranked.filter((x) => x.r.passedAt && !x.r.failed);
  console.log(`\nReached +$${TARGET} without failing MLL: ${passed.length ? passed.map((b) => b.name.replace(/^\d+\.\s*/, "") + ` (@${b.r.passedAt} trades)`).join(", ") : "none"}`);
  console.log(`Skp=signals skipped (stop > $${MAX_TRADE_RISK} cap)  Lck=days hit the loss lockout. Caveat: 13 days = tiny sample, ranks ideas not verdicts.`);
})();
