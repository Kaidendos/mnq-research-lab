// =============================================================
//  backtest-lab.js — STRATEGY LAB. Evaluate every strategy/variant across
//  MULTIPLE history samples at once (13-day CSV / 58-day Yahoo / 89-day CSV)
//  so nothing gets adopted on small-sample noise. The 13-day is the fast
//  dev loop; a candidate only "passes" if it ALSO holds up out-of-sample on
//  the 58- and 89-day windows it was NOT tuned on.
//
//  DATA-ONLY / TopStep-compliant: reads history, never places an order.
//  Run:  node backtest-lab.js
//
//  Goal screen: win% >= 60 AND positive net on ALL samples AND survivable
//  drawdown (maxDD + worst-day inside the $50k Combine limits at size).
//
//  Consumes bars = [{ t, o, h, l, c, v }], t = epoch SECONDS, ascending.
// =============================================================
"use strict";

const fs = require("fs");
require("./public/indicators.js");
require("./public/simple.js");
require("./public/orb.js");
require("./public/meanrev.js");
const I = globalThis.Indicators;
const Simple = globalThis.Simple;
const ORB = globalThis.ORB;
const MeanRev = globalThis.MeanRev;
const Yahoo = require("./yahoo.js");

const PV_MNQ = 2;
const DLL = 1000;   // TopStep $50k Combine daily loss limit
const MLL = 2000;   // trailing max loss limit
const SIZE = 3;     // MNQ contracts to report survival at (ruleset rec for v1.1: 1-3)

const CSV_13 = "C:\\Users\\kaide\\Downloads\\CME_MINI_DL_MNQ1!, 5.csv";
const CSV_89 = "C:\\Users\\kaide\\Downloads\\CME_MINI_DL_MNQ1!, 5 (1).csv";

const dayKeyOf = Simple.dayKeyOf;
const f = (x, d = 0) => (x == null ? "—" : Number(x).toFixed(d));

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

// ---- Unified exit sim: stop-first on ties, flat by EOD, optional BE latch. ----
function simulateTrade(bars, entryIdx, sig) {
  const dayKey = dayKeyOf(bars[entryIdx].t);
  const isLong = sig.dir === 1;
  const entry = sig.entry;
  let beLatched = false;
  for (let k = entryIdx + 1; k < bars.length; k++) {
    if (dayKeyOf(bars[k].t) !== dayKey) break;
    const b = bars[k];
    const stopLvl = (sig.useBE && beLatched) ? entry : sig.stop;
    const hitStop = isLong ? b.l <= stopLvl : b.h >= stopLvl;
    const hitTgt = isLong ? b.h >= sig.target : b.l <= sig.target;
    if (hitStop) return { pts: isLong ? stopLvl - entry : entry - stopLvl, exit: "stop", exitIdx: k };
    if (hitTgt) return { pts: isLong ? sig.target - entry : entry - sig.target, exit: "target", exitIdx: k };
    if (sig.useBE && !beLatched) {
      const reached = isLong ? b.h >= entry + sig.beTrigPts : b.l <= entry - sig.beTrigPts;
      if (reached) beLatched = true;
    }
  }
  let last = entryIdx;
  for (let k = entryIdx + 1; k < bars.length && dayKeyOf(bars[k].t) === dayKey; k++) last = k;
  return { pts: isLong ? bars[last].c - entry : entry - bars[last].c, exit: "close", exitIdx: last };
}

function tally(trades) {
  const wins = trades.filter((t) => t.pts > 0);
  const grossWin = wins.reduce((s, t) => s + t.pts, 0);
  const grossLoss = Math.abs(trades.filter((t) => t.pts <= 0).reduce((s, t) => s + t.pts, 0));
  const netPts = trades.reduce((s, t) => s + t.pts, 0);
  let peak = 0, cum = 0, maxDD = 0;
  for (const t of trades) { cum += t.pts; peak = Math.max(peak, cum); maxDD = Math.max(maxDD, peak - cum); }
  let streak = 0, maxLossStreak = 0;
  for (const t of trades) { if (t.pts <= 0) { streak++; maxLossStreak = Math.max(maxLossStreak, streak); } else streak = 0; }
  const byDay = new Map();
  for (const t of trades) byDay.set(t.date, (byDay.get(t.date) || 0) + t.pts);
  const worstDayPts = trades.length ? Math.min(0, ...byDay.values()) : 0;
  const tradingDays = byDay.size || 1;
  return {
    n: trades.length, winRate: trades.length ? (wins.length / trades.length) * 100 : 0,
    pf: grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? Infinity : 0),
    netPts, ddPts: maxDD, worstDayPts, tradingDays, maxLossStreak,
  };
}

function etDate(s) { return new Date(s * 1000).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" }); }

// ---- Mean-rev precomputed signal builder (O(n)); knobs: stop mult/cap + target fraction toward the mean. ----
function meanRevSignals(bars, { mult = 1.0, cap = null, tgtFrac = 1.0 } = {}) {
  const C = MeanRev.CONFIG;
  const close = bars.map((b) => b.c), high = bars.map((b) => b.h), low = bars.map((b) => b.l);
  const basis = I.sma(close, C.bbLen), dev = I.stdev(close, C.bbLen);
  const lb = basis.map((v, k) => (v == null ? null : v - C.bbMult * dev[k]));
  const ub = basis.map((v, k) => (v == null ? null : v + C.bbMult * dev[k]));
  const rsi = I.rsi(close, C.rsiLen);
  const { adx } = I.dmi(high, low, close, C.adxLen, C.adxLen);
  const ema = I.ema(close, C.trendLen);
  const atr = I.atr(high, low, close, C.atrLen);
  const sL = close.map((x, k) => lb[k] != null && rsi[k] != null && x <= lb[k] && rsi[k] <= C.rsiOS);
  const sS = close.map((x, k) => ub[k] != null && rsi[k] != null && x >= ub[k] && rsi[k] >= C.rsiOB);
  const xu = I.crossover(close, lb), xd = I.crossunder(close, ub);
  const sig = new Array(bars.length).fill(null);
  for (let i = 1; i < bars.length; i++) {
    if (basis[i] == null || ema[i] == null || adx[i] == null || atr[i] == null) continue;
    if (!MeanRev.isInRTH(bars[i].t)) continue;
    if (!(adx[i] < C.adxMax)) continue;
    let stopPts = mult * atr[i];
    if (cap != null) stopPts = Math.min(stopPts, cap);
    const rl = xu[i] && I.barsSince(sL, i) <= C.confirmBars;
    const rs = xd[i] && I.barsSince(sS, i) <= C.confirmBars;
    const e = close[i];
    if (rl && e > ema[i]) sig[i] = { dir: 1, entry: e, stop: e - stopPts, target: e + tgtFrac * (basis[i] - e) };
    else if (rs && e < ema[i]) sig[i] = { dir: -1, entry: e, stop: e + stopPts, target: e - tgtFrac * (e - basis[i]) };
  }
  return sig;
}

// Walk a precomputed signal array, one position at a time.
function runSignals(bars, sig) {
  const trades = [];
  let i = 1;
  while (i < bars.length) {
    if (sig[i]) { const r = simulateTrade(bars, i, sig[i]); trades.push({ date: etDate(bars[i].t), pts: r.pts }); i = r.exitIdx + 1; }
    else i++;
  }
  return tally(trades);
}

function runSimple(bars, opts) {
  const pre = Simple.prepare(bars, opts);
  const C = pre.C;
  const trades = [];
  let i = 1, curDay = null, dayPnLUSD = 0;
  while (i < bars.length) {
    const dk = dayKeyOf(bars[i].t);
    if (dk !== curDay) { curDay = dk; dayPnLUSD = 0; }
    if (dayPnLUSD <= -C.dayLoss) { i++; continue; }
    const s = Simple.computeSimple(bars, i, opts, pre);
    if (s.signal === "BUY" || s.signal === "SELL") {
      const r = simulateTrade(bars, i, s);
      trades.push({ date: etDate(bars[i].t), pts: r.pts });
      dayPnLUSD += r.pts * PV_MNQ;
      i = r.exitIdx + 1;
    } else i++;
  }
  return tally(trades);
}

function runORB(bars, opts) {
  const C = ORB.CONFIG;
  const orEnd = ORB.hhmmToMins(C.openHHMM) + C.orMinutes;
  const entryEnd = ORB.hhmmToMins(C.entryEndHHMM);
  const byDay = new Map();
  for (let i = 0; i < bars.length; i++) { const k = dayKeyOf(bars[i].t); if (!byDay.has(k)) byDay.set(k, []); byDay.get(k).push(i); }
  const trades = [];
  for (const idxs of byDay.values()) {
    for (const i of idxs) {
      const mins = ORB.etParts(bars[i].t).mins;
      if (mins < orEnd || mins >= entryEnd) continue;
      const s = ORB.computeORB(bars, i, opts);
      if (s.signal !== "BUY" && s.signal !== "SELL") continue;
      const r = simulateTrade(bars, i, s);
      trades.push({ date: etDate(bars[i].t), pts: r.pts });
      break;
    }
  }
  return tally(trades);
}

// ---- Strategy roster: each returns a tally for a given bar set. ----
const STRATS = [
  { name: "MeanRev base (1.0ATR, tgt=mean)", run: (b) => runSignals(b, meanRevSignals(b, { mult: 1.0, tgtFrac: 1.0 })) },
  { name: "MeanRev 0.50ATR", run: (b) => runSignals(b, meanRevSignals(b, { mult: 0.5, tgtFrac: 1.0 })) },
  { name: "MeanRev cap12pt", run: (b) => runSignals(b, meanRevSignals(b, { mult: 1.0, cap: 12, tgtFrac: 1.0 })) },
  { name: "MeanRev tgt0.75 mean", run: (b) => runSignals(b, meanRevSignals(b, { mult: 1.0, tgtFrac: 0.75 })) },
  { name: "MeanRev tgt0.50 mean", run: (b) => runSignals(b, meanRevSignals(b, { mult: 1.0, tgtFrac: 0.5 })) },
  { name: "MeanRev tgt0.50 +0.75ATR", run: (b) => runSignals(b, meanRevSignals(b, { mult: 0.75, tgtFrac: 0.5 })) },
  { name: "MeanRev tgt0.50 +cap20", run: (b) => runSignals(b, meanRevSignals(b, { mult: 1.0, cap: 20, tgtFrac: 0.5 })) },
  { name: "Simple v5 (60/32)", run: (b) => runSimple(b, Simple.PRESETS.v5) },
  { name: "Simple v3 (50/50)", run: (b) => runSimple(b, Simple.PRESETS.v3) },
  { name: "Simple v5loose", run: (b) => runSimple(b, Simple.PRESETS.v5loose) },
  { name: "ORB v5 filter ON", run: (b) => runORB(b, { useRangeFilter: true, maxRangePts: 70 }) },
  { name: "ORB v5 filter OFF", run: (b) => runORB(b, { useRangeFilter: false }) },
];

(async () => {
  const samples = [
    { name: "13d", bars: loadCsv(CSV_13) },
    { name: "58d", bars: await Yahoo.fetchBars({ interval: "5m", range: "60d" }) },
    { name: "89d", bars: loadCsv(CSV_89) },
  ];
  for (const s of samples) s.days = new Set(s.bars.map((b) => dayKeyOf(b.t))).size;

  console.log(`STRATEGY LAB — ${samples.map((s) => `${s.name}=${s.days}d/${s.bars.length}bars`).join("  ")}`);
  console.log(`Metrics per 1 MNQ ($2/pt). Survival flagged at ${SIZE} MNQ ($${2 * SIZE}/pt) vs DLL $${DLL} / MLL $${MLL}.`);
  console.log(`Goal screen: win% >= 60 AND net>0 on ALL 3 samples AND drawdown survivable.\n`);

  // header
  const cols = samples.map((s) => s.name);
  let hdr = "Strategy".padEnd(32) + cols.map((c) => `${c} win%/PF/net/maxDD`.padStart(26)).join("");
  console.log(hdr);
  console.log("-".repeat(hdr.length));

  const results = [];
  for (const strat of STRATS) {
    const per = samples.map((s) => ({ s, r: strat.run(s.bars) }));
    results.push({ strat, per });
    let row = strat.name.padEnd(32);
    for (const { r } of per) {
      const cell = `${f(r.winRate)}% ${r.pf === Infinity ? "inf" : f(r.pf, 2)} ${(r.netPts >= 0 ? "+" : "") + f(r.netPts)} dd${f(r.ddPts)}`;
      row += cell.padStart(26);
    }
    console.log(row);
  }

  // ---- Goal screen ----
  console.log(`\n=== GOAL SCREEN (>=60% win + net>0 on all 3 + survivable @ ${SIZE} MNQ) ===`);
  let any = false;
  for (const { strat, per } of results) {
    const allWin60 = per.every((p) => p.r.winRate >= 60);
    const allPos = per.every((p) => p.r.netPts > 0);
    const worstDay$ = Math.min(...per.map((p) => p.r.worstDayPts)) * PV_MNQ * SIZE;
    const worstDD$ = Math.max(...per.map((p) => p.r.ddPts)) * PV_MNQ * SIZE;
    const survives = -worstDay$ < DLL && worstDD$ < MLL;
    if (allWin60 && allPos) {
      any = true;
      const win = per.map((p) => f(p.r.winRate) + "%").join("/");
      console.log(`  ${survives ? "✅" : "⚠️ "} ${strat.name.padEnd(30)} win ${win}  | worstDay $${f(worstDay$)} (DLL $${DLL})  maxDD $${f(worstDD$)} (MLL $${MLL})  ${survives ? "SURVIVES" : "RISK at " + SIZE + " MNQ"}`);
    }
  }
  if (!any) console.log("  (none clear >=60% win on all 3 samples — see table; closest candidates are the higher-win-rate rows)");

  // ---- NET-PER-DRAWDOWN RANKING (Combine objective: reach +$3,000 before -$2,000 trailing) ----
  // Max safe size = largest MNQ where the WORST of {58d,89d} drawdown stays under 80% of the MLL
  // AND the worst day stays under 80% of the DLL. Then net + days-to-$3k are shown at that size.
  const MLL_CAP = 0.8 * MLL, DLL_CAP = 0.8 * DLL;
  function safeSize(per) {
    const dd = Math.max(per[1].r.ddPts, per[2].r.ddPts);            // worst drawdown across robust samples
    const wd = Math.min(per[1].r.worstDayPts, per[2].r.worstDayPts); // most-negative day across robust samples
    const byMLL = dd > 0 ? MLL_CAP / (dd * PV_MNQ) : Infinity;
    const byDLL = wd < 0 ? DLL_CAP / (-wd * PV_MNQ) : Infinity;
    return Math.max(0, Math.floor(Math.min(byMLL, byDLL)));
  }
  console.log(`\n=== NET-PER-DRAWDOWN RANKING (profit-first; reach +$${3000} before -$${MLL} trailing) ===`);
  console.log(`Ranked by 89d net/maxDD. "Safe MNQ" keeps worst {58,89}d drawdown < $${MLL_CAP} & worst day < $${DLL_CAP}. Min 12 trades & positive on 58d+89d.`);
  const hdr2 = "Strategy".padEnd(32) + "58d n/DD".padStart(9) + "89d n/DD".padStart(9) + "safeMNQ".padStart(8) + "net@safe(89d)".padStart(14) + "~days→$3k".padStart(10) + "worstStreak".padStart(12) + "89d win%".padStart(9);
  console.log(hdr2);
  console.log("-".repeat(hdr2.length));
  const ranked = results
    .filter(({ per }) => per[2].r.n >= 12 && per[1].r.netPts > 0 && per[2].r.netPts > 0)
    .map(({ strat, per }) => {
      const eff58 = per[1].r.ddPts > 0 ? per[1].r.netPts / per[1].r.ddPts : Infinity;
      const eff89 = per[2].r.ddPts > 0 ? per[2].r.netPts / per[2].r.ddPts : Infinity;
      const N = safeSize(per);
      const net89 = per[2].r.netPts * PV_MNQ * N;
      const perDay = per[2].r.tradingDays ? net89 / per[2].r.tradingDays : 0;
      const days3k = perDay > 0 ? Math.ceil(3000 / perDay) : Infinity;
      return { name: strat.name, eff58, eff89, N, net89, days3k, streak: Math.max(per[1].r.maxLossStreak, per[2].r.maxLossStreak), win89: per[2].r.winRate };
    })
    .sort((a, b) => b.eff89 - a.eff89);
  for (const x of ranked) {
    console.log(
      x.name.padEnd(32) + f(x.eff58, 2).padStart(9) + f(x.eff89, 2).padStart(9) + (x.N + " MNQ").padStart(8) +
      ("+$" + f(x.net89)).padStart(14) + (x.days3k === Infinity ? "—" : "~" + x.days3k).padStart(10) +
      (x.streak + "L").padStart(12) + (f(x.win89) + "%").padStart(9)
    );
  }
  console.log(`\nHigher 89d n/DD = more profit per unit of risk. Watch worstStreak: a low-win strategy with a long losing run can still tag the trailing MLL out-of-sample.`);
  console.log(`Reminder: 13d is ~8-15 trades — treat its win% as noise. The 58d & 89d columns are the real test.`);
})().catch((e) => { console.error("lab error:", e.message); process.exit(1); });
