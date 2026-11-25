// =============================================================
//  backtest.js — runs the v5 strategy logic over historical NQ data
//  so we can iterate on the edge WITHOUT TradingView screenshots.
//  Mirrors the Pine v5: BB12/2, MACD12/26/9, RSI7, ADX14, EMA200,
//  ADR-20 stop(10%)/target(15%), +1R breakeven, RTH session,
//  daily-loss lockout, EOD flatten.
//
//  Equity (for max drawdown) is sampled each bar INCLUDING open-trade
//  MTM — that's the number TopStep's trailing Max-Loss-Limit cares about.
//
//  Run:  node backtest.js
// =============================================================
"use strict";
require("./public/indicators.js");
const I = globalThis.Indicators;

const SYMBOL = process.env.SYMBOL || "NQ=F";
const POINT_VALUE = 2;   // MNQ $2/pt (so DD maps to TopStep sizing per MNQ)
const QTY = 1;
const DAILY_LOSS = 1000; // $ daily lockout (per account, not per contract)

async function yget(interval, range) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(SYMBOL)}?interval=${interval}&range=${range}`;
  const r = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
  const j = await r.json();
  const res = j.chart.result[0];
  const ts = res.timestamp || [];
  const q = res.indicators.quote[0];
  const bars = [];
  for (let i = 0; i < ts.length; i++) {
    if (q.open[i] == null || q.high[i] == null || q.low[i] == null || q.close[i] == null) continue;
    bars.push({ t: ts[i], o: q.open[i], h: q.high[i], l: q.low[i], c: q.close[i] });
  }
  return bars;
}

function etParts(epochSec) {
  const d = new Date(epochSec * 1000);
  const et = new Date(d.toLocaleString("en-US", { timeZone: "America/New_York" }));
  return { day: et.getDay(), mins: et.getHours() * 60 + et.getMinutes(),
           date: et.toLocaleDateString("en-US", { timeZone: "America/New_York" }) };
}
function inRTH(epochSec) {
  const p = etParts(epochSec);
  if (p.day === 0 || p.day === 6) return false;
  return p.mins >= 9 * 60 + 30 && p.mins < 16 * 60;
}

// Build a map: ET-date -> ADR20 using daily bars, shifted by 1 (no lookahead).
function buildAdrMap(daily) {
  const ranges = daily.map((b) => b.h - b.l);
  const map = {};
  for (let i = 0; i < daily.length; i++) {
    const start = Math.max(0, i - 20);
    const slice = ranges.slice(start, i); // up to but NOT including today
    if (slice.length === 0) { map[daily[i].dateKey] = null; continue; }
    map[daily[i].dateKey] = slice.reduce((a, b) => a + b, 0) / slice.length;
  }
  return map;
}

function runBacktest(bars5, adrByDate, cfg) {
  const close = bars5.map((b) => b.c);
  const high = bars5.map((b) => b.h);
  const low = bars5.map((b) => b.l);
  const n = bars5.length;

  const basis = I.sma(close, 12);
  const dev = I.stdev(close, 12);
  const upper = basis.map((v, i) => (v == null ? null : v + 2 * dev[i]));
  const lower = basis.map((v, i) => (v == null ? null : v - 2 * dev[i]));
  const { macdLine, signalLine } = I.macd(close, 12, 26, 9);
  const rsi = I.rsi(close, 7);
  const { adx } = I.dmi(high, low, close, 14, 14);
  const ema200 = I.ema(close, 200);
  const crossUp = I.crossover(macdLine, signalLine);
  const crossDn = I.crossunder(macdLine, signalLine);

  let pos = null;
  let realized = 0;
  let peak = 0, maxDD = 0;
  const trades = [];
  let curDate = null, dayPnLStart = 0, locked = false;

  const longSignal = new Array(n).fill(false);
  const shortSignal = new Array(n).fill(false);
  for (let i = 0; i < n; i++) {
    if (ema200[i] == null || adx[i] == null || rsi[i] == null) continue;
    const macdUpOK = I.barsSince(crossUp, i) <= cfg.lookback - 1 && macdLine[i] > signalLine[i];
    const macdDnOK = I.barsSince(crossDn, i) <= cfg.lookback - 1 && macdLine[i] < signalLine[i];
    const regimeOK = adx[i] > cfg.adxMin;
    const inSess = inRTH(bars5[i].t);
    longSignal[i] = cfg.allowLong && macdUpOK && rsi[i] > cfg.rsiLongMin &&
      close[i] < upper[i] && regimeOK && inSess && close[i] > ema200[i];
    shortSignal[i] = cfg.allowShort && macdDnOK && rsi[i] < cfg.rsiShortMax &&
      close[i] > lower[i] && regimeOK && inSess && close[i] < ema200[i];
  }

  for (let i = 1; i < n; i++) {
    const t = bars5[i].t;
    const p = etParts(t);
    if (p.date !== curDate) { curDate = p.date; dayPnLStart = realized; locked = false; }
    const sessNow = inRTH(t);
    const sessNext = i + 1 < n ? inRTH(bars5[i + 1].t) : false;

    if (pos) {
      const stopPts = pos.adr * cfg.stopPct;
      if (cfg.useBE && !pos.beArmed) {
        if (pos.dir === 1 && high[i] >= pos.entry + stopPts) { pos.stop = pos.entry; pos.beArmed = true; }
        if (pos.dir === -1 && low[i] <= pos.entry - stopPts) { pos.stop = pos.entry; pos.beArmed = true; }
      }
      let exitPx = null;
      if (pos.dir === 1) {
        if (low[i] <= pos.stop) exitPx = pos.stop;
        else if (high[i] >= pos.target) exitPx = pos.target;
      } else {
        if (high[i] >= pos.stop) exitPx = pos.stop;
        else if (low[i] <= pos.target) exitPx = pos.target;
      }
      if (exitPx == null && sessNow && !sessNext) exitPx = close[i];
      if (exitPx != null) {
        const pts = (exitPx - pos.entry) * pos.dir;
        realized += pts * POINT_VALUE * QTY;
        trades.push(pts * POINT_VALUE * QTY);
        pos = null;
      }
    }

    if (realized - dayPnLStart <= -DAILY_LOSS) locked = true;

    if (!pos && !locked) {
      const sIdx = i - 1;
      const adr = adrByDate[etParts(bars5[sIdx].t).date];
      if (adr) {
        if (longSignal[sIdx]) {
          const entry = bars5[i].o;
          pos = { dir: 1, entry, stop: entry - adr * cfg.stopPct, target: entry + adr * cfg.tgtPct, adr, beArmed: false };
        } else if (shortSignal[sIdx]) {
          const entry = bars5[i].o;
          pos = { dir: -1, entry, stop: entry + adr * cfg.stopPct, target: entry - adr * cfg.tgtPct, adr, beArmed: false };
        }
      }
    }

    let openPnl = 0;
    if (pos) openPnl = (close[i] - pos.entry) * pos.dir * POINT_VALUE * QTY;
    const eq = realized + openPnl;
    if (eq > peak) peak = eq;
    if (peak - eq > maxDD) maxDD = peak - eq;
  }

  const wins = trades.filter((x) => x > 0);
  const losses = trades.filter((x) => x <= 0);
  const gp = wins.reduce((a, b) => a + b, 0);
  const gl = -losses.reduce((a, b) => a + b, 0);
  return {
    net: realized, maxDD, trades: trades.length,
    winRate: trades.length ? (wins.length / trades.length) * 100 : 0,
    pf: gl === 0 ? Infinity : gp / gl,
    ratio: maxDD === 0 ? Infinity : realized / maxDD,
  };
}

(async () => {
  const bars5 = await yget("5m", "60d");
  const dailyRaw = await yget("1d", "6mo");
  dailyRaw.forEach((b) => (b.dateKey = etParts(b.t).date));
  const adrMap = buildAdrMap(dailyRaw);
  const adrByDate = {};
  let lastAdr = null;
  for (const d of dailyRaw) { if (adrMap[d.dateKey] != null) lastAdr = adrMap[d.dateKey]; adrByDate[d.dateKey] = lastAdr; }
  for (const b of bars5) { const k = etParts(b.t).date; if (!(k in adrByDate)) adrByDate[k] = lastAdr; }

  const base = { lookback: 2, rsiLongMin: 60, rsiShortMax: 32, adxMin: 20,
                 stopPct: 0.10, tgtPct: 0.15, useBE: true, allowLong: true, allowShort: true };
  const variants = {
    "stop10 tgt15 (base)": { ...base, stopPct: 0.10, tgtPct: 0.15 },
    "stop10 tgt20":        { ...base, stopPct: 0.10, tgtPct: 0.20 },
    "stop10 tgt25":        { ...base, stopPct: 0.10, tgtPct: 0.25 },
    "stop10 tgt30":        { ...base, stopPct: 0.10, tgtPct: 0.30 },
    "stop08 tgt20":        { ...base, stopPct: 0.08, tgtPct: 0.20 },
    "stop08 tgt24":        { ...base, stopPct: 0.08, tgtPct: 0.24 },
    "stop12 tgt24":        { ...base, stopPct: 0.12, tgtPct: 0.24 },
    "stop10 tgt20 noBE":   { ...base, stopPct: 0.10, tgtPct: 0.20, useBE: false },
  };

  console.log(`Data: ${bars5.length} 5-min bars over 60d. POINT_VALUE=$${POINT_VALUE}/pt (MNQ), qty ${QTY}.`);
  console.log("(net & maxDD are per 1 MNQ; multiply by contracts. TopStep bust = $2,000 trailing.)\n");
  const pad = (s, w) => String(s).padEnd(w);
  console.log(pad("config", 24) + pad("net$", 9) + pad("maxDD$", 9) + pad("ratio", 8) + pad("PF", 7) + pad("win%", 7) + "trades");
  for (const [name, cfg] of Object.entries(variants)) {
    const r = runBacktest(bars5, adrByDate, cfg);
    console.log(
      pad(name, 24) +
      pad(r.net.toFixed(0), 9) +
      pad(r.maxDD.toFixed(0), 9) +
      pad(r.ratio.toFixed(2), 8) +
      pad(r.pf.toFixed(2), 7) +
      pad(r.winRate.toFixed(0), 7) +
      r.trades
    );
  }
})();
