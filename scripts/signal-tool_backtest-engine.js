// =============================================================
//  backtest-engine.js — ruleset-driven backtest + final presentation.
//
//  The whole pipeline the user asked for, in one place:
//    1. reads the machine-readable ruleset (strategy-ruleset.json)
//    2. pulls historical NQ 5-min futures data (Yahoo, ~50 trading days,
//       cached to data/nq-5m.json so reruns are deterministic)
//    3. replays the strategy EXACTLY as it trades (logic mirrors
//       public/meanrev.js line-for-line; the ruleset supplies every number),
//       for both v1.1 (floating ATR stop) and the v1.2 candidate (12pt cap)
//    4. writes a final presentation to report.html (+ console summary)
//
//  DATA-ONLY / TopStep-compliant: reads history, never places an order.
//  Run:  node backtest-engine.js           (fetch fresh data)
//        node backtest-engine.js --cache    (reuse data/nq-5m.json)
//
//  IMPORTANT HONESTY: ~50 trading days is far better than the 11-day
//  ProjectX sample, but still NOT a multi-regime, multi-year validation.
//  Read this as a stronger sanity check, not a final verdict.
// =============================================================
"use strict";

const fs = require("fs");
const path = require("path");
require("./public/indicators.js");
const I = globalThis.Indicators;

const RULESET = JSON.parse(fs.readFileSync(path.join(__dirname, "strategy-ruleset.json"), "utf8"));
const DATA_DIR = path.join(__dirname, "data");
const DATA_FILE = path.join(DATA_DIR, "nq-5m.json");
const REPORT_FILE = path.join(__dirname, "report.html");

const PV = RULESET.instrument.point_value_usd; // { NQ:20, MNQ:2 }
const IND = RULESET.indicators;
const ENTRY = RULESET.entry;
const EXIT = RULESET.exit;
const TARGET_USD = RULESET.risk.topstep_50k_combine.profit_target_usd;
const DAILY_LIMIT = RULESET.risk.topstep_50k_combine.daily_loss_limit_usd;
const MLL = RULESET.risk.topstep_50k_combine.trailing_max_loss_limit_usd;
const ADX_MAX = 25; // ruleset filters.regime: "adx < 25"

// --- data --------------------------------------------------------------
async function fetchYahoo() {
  const url = "https://query1.finance.yahoo.com/v8/finance/chart/NQ=F?interval=5m&range=60d";
  const r = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
  if (!r.ok) throw new Error("Yahoo " + r.status);
  const j = await r.json();
  const res = j.chart.result[0];
  const t = res.timestamp || [];
  const q = res.indicators.quote[0];
  const bars = [];
  for (let i = 0; i < t.length; i++) {
    if (q.open[i] == null || q.high[i] == null || q.low[i] == null || q.close[i] == null) continue;
    bars.push({ t: t[i], o: q.open[i], h: q.high[i], l: q.low[i], c: q.close[i], v: q.volume[i] || 0 });
  }
  return bars;
}

async function getBars(useCache) {
  if (useCache && fs.existsSync(DATA_FILE)) {
    return JSON.parse(fs.readFileSync(DATA_FILE, "utf8"));
  }
  const bars = await fetchYahoo();
  if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
  fs.writeFileSync(DATA_FILE, JSON.stringify(bars));
  return bars;
}

// --- time helpers (ET) -------------------------------------------------
function etParts(epochSec) {
  const et = new Date(new Date(epochSec * 1000).toLocaleString("en-US", { timeZone: "America/New_York" }));
  return { y: et.getFullYear(), mo: et.getMonth(), d: et.getDate(), day: et.getDay(), mins: et.getHours() * 60 + et.getMinutes() };
}
function dayKeyOf(epochSec) { const p = etParts(epochSec); return `${p.y}-${p.mo}-${p.d}`; }
function etDate(epochSec) { return new Date(epochSec * 1000).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" }); }
function isInRTH(epochSec) {
  const p = etParts(epochSec);
  if (p.day === 0 || p.day === 6) return false;
  return p.mins >= 570 && p.mins < 960; // 09:30–16:00 ET
}

// --- signal (mirrors public/meanrev.js, parameterized by the ruleset) --
// Returns a per-bar array; each tradable bar holds a signal object, else null.
function buildSignals(bars, hardCapPts) {
  const close = bars.map((b) => b.c), high = bars.map((b) => b.h), low = bars.map((b) => b.l);
  const basis = I.sma(close, IND.bollinger.length);
  const dev = I.stdev(close, IND.bollinger.length);
  const lowerBB = basis.map((v, k) => (v == null ? null : v - IND.bollinger.mult * dev[k]));
  const upperBB = basis.map((v, k) => (v == null ? null : v + IND.bollinger.mult * dev[k]));
  const rsi = I.rsi(close, IND.rsi.length);
  const { adx } = I.dmi(high, low, close, IND.adx.length, IND.adx.length);
  const ema200 = I.ema(close, IND.ema_trend.length);
  const atr = I.atr(high, low, close, IND.atr.length);

  const stretchLong = close.map((c, k) => lowerBB[k] != null && rsi[k] != null && c <= lowerBB[k] && rsi[k] <= IND.rsi.oversold);
  const stretchShort = close.map((c, k) => upperBB[k] != null && rsi[k] != null && c >= upperBB[k] && rsi[k] >= IND.rsi.overbought);
  const xUp = I.crossover(close, lowerBB);
  const xDn = I.crossunder(close, upperBB);

  const sigs = new Array(bars.length).fill(null);
  for (let i = 1; i < bars.length; i++) {
    if (basis[i] == null || ema200[i] == null || adx[i] == null || atr[i] == null) continue;
    if (!isInRTH(bars[i].t)) continue;
    if (!(adx[i] < ADX_MAX)) continue; // only fade in a ranging regime
    const upBias = close[i] > ema200[i], dnBias = close[i] < ema200[i];
    const reclaimLong = xUp[i] && I.barsSince(stretchLong, i) <= ENTRY.confirm_bars;
    const reclaimShort = xDn[i] && I.barsSince(stretchShort, i) <= ENTRY.confirm_bars;

    if (reclaimLong && upBias) {
      let stopPts = EXIT.stop.atr_stop_mult * atr[i];
      if (hardCapPts != null) stopPts = Math.min(stopPts, hardCapPts);
      const entry = close[i];
      sigs[i] = { dir: 1, entry, stop: entry - stopPts, target: basis[i], stopPts };
    } else if (reclaimShort && dnBias) {
      let stopPts = EXIT.stop.atr_stop_mult * atr[i];
      if (hardCapPts != null) stopPts = Math.min(stopPts, hardCapPts);
      const entry = close[i];
      sigs[i] = { dir: -1, entry, stop: entry + stopPts, target: basis[i], stopPts };
    }
  }
  return sigs;
}

// --- exit sim (conservative ties, flat by EOD) -------------------------
function simulateTrade(bars, entryIdx, sig) {
  const dayKey = dayKeyOf(bars[entryIdx].t);
  const isLong = sig.dir === 1, entry = sig.entry;
  for (let k = entryIdx + 1; k < bars.length; k++) {
    if (dayKeyOf(bars[k].t) !== dayKey) break;
    const b = bars[k];
    const hitStop = isLong ? b.l <= sig.stop : b.h >= sig.stop;
    const hitTgt = isLong ? b.h >= sig.target : b.l <= sig.target;
    if (hitStop) return { pts: isLong ? sig.stop - entry : entry - sig.stop, exit: "stop", exitIdx: k };
    if (hitTgt) return { pts: isLong ? sig.target - entry : entry - sig.target, exit: "target", exitIdx: k };
  }
  let last = entryIdx;
  for (let k = entryIdx + 1; k < bars.length && dayKeyOf(bars[k].t) === dayKey; k++) last = k;
  const px = bars[last].c;
  return { pts: isLong ? px - entry : entry - px, exit: "close", exitIdx: last };
}

function runVariant(bars, hardCapPts) {
  const sigs = buildSignals(bars, hardCapPts);
  const trades = [];
  let maxStopPts = 0, i = 1;
  while (i < bars.length) {
    if (sigs[i]) {
      maxStopPts = Math.max(maxStopPts, sigs[i].stopPts);
      const res = simulateTrade(bars, i, sigs[i]);
      trades.push({ date: etDate(bars[i].t), dayKey: dayKeyOf(bars[i].t), dir: sigs[i].dir === 1 ? "BUY" : "SELL", pts: res.pts, exit: res.exit });
      i = res.exitIdx + 1;
    } else i++;
  }
  return tally(trades, maxStopPts);
}

function tally(trades, maxStopPts) {
  const wins = trades.filter((t) => t.pts > 0), losses = trades.filter((t) => t.pts <= 0);
  const grossWin = wins.reduce((s, t) => s + t.pts, 0);
  const grossLoss = Math.abs(losses.reduce((s, t) => s + t.pts, 0));
  const netPts = trades.reduce((s, t) => s + t.pts, 0);
  const worstPts = trades.reduce((m, t) => Math.min(m, t.pts), 0);
  let peak = 0, cum = 0, maxDD = 0;
  for (const t of trades) { cum += t.pts; peak = Math.max(peak, cum); maxDD = Math.max(maxDD, peak - cum); }
  const byDay = new Map();
  for (const t of trades) byDay.set(t.dayKey, (byDay.get(t.dayKey) || 0) + t.pts);
  const worstDayPts = trades.length ? Math.min(0, ...byDay.values()) : 0;
  return {
    n: trades.length, wins: wins.length, losses: losses.length,
    winRate: trades.length ? (wins.length / trades.length) * 100 : 0,
    pf: grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? Infinity : 0),
    netPts, maxDDpts: maxDD, worstPts, worstDayPts, maxStopPts,
    tradingDays: byDay.size, trades,
  };
}

// --- $ scaling ---------------------------------------------------------
function scale(r, contracts) {
  const pv = PV.MNQ * contracts;
  const net = r.netPts * pv;
  const perDay = r.tradingDays ? net / r.tradingDays : 0;
  return {
    contracts, net, worstTrade: r.worstPts * pv, worstDay: r.worstDayPts * pv,
    maxStop$: r.maxStopPts * pv, maxDD$: r.maxDDpts * pv,
    daysToTarget: perDay > 0 ? Math.ceil(TARGET_USD / perDay) : Infinity,
    mllPctWorstDay: (Math.abs(r.worstDayPts * pv) / MLL) * 100,
    dailyOK: Math.abs(r.worstDayPts * pv) < DAILY_LIMIT,
  };
}

const money = (x) => (x >= 0 ? "+$" : "-$") + Math.abs(Math.round(x)).toLocaleString();
const f = (x, d = 2) => (x == null ? "—" : Number(x).toFixed(d));

// --- presentation (report.html) ---------------------------------------
function buildReport(meta, v11, v12) {
  const sizingRows = (r, label, capped) => [1, 3, 5].map((c) => {
    const s = scale(r, c);
    return `<tr><td>${label}</td><td>${c} MNQ</td><td>${money(s.net)}</td><td>${money(s.worstTrade)}${capped ? " <span class=cap>(capped)</span>" : ""}</td><td>${money(s.worstDay)}</td><td>${s.dailyOK ? "✅" : "❌"}</td><td>${f(s.mllPctWorstDay, 0)}%</td><td>~${s.daysToTarget}</td></tr>`;
  }).join("");

  return `<!doctype html><html><head><meta charset="utf-8"><title>NQ Mean-Reversion — Backtest Presentation</title>
<style>
body{font:15px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;max-width:980px;margin:32px auto;padding:0 20px;color:#1a1a2e;background:#fafafc}
h1{font-size:26px;margin-bottom:4px}h2{margin-top:34px;border-bottom:2px solid #e0e0ec;padding-bottom:6px}
.sub{color:#666;margin-top:0}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px}
th,td{border:1px solid #dcdce6;padding:7px 10px;text-align:center}th{background:#2d2d44;color:#fff}
td:first-child,th:first-child{text-align:left}
.win{color:#1a8a4a;font-weight:600}.lose{color:#c0392b;font-weight:600}
.box{background:#fff;border:1px solid #e0e0ec;border-radius:10px;padding:16px 20px;margin:14px 0}
.warn{background:#fff8e6;border-color:#f0c040}
.verdict{background:#eafaf0;border-color:#1a8a4a}
.cap{color:#1a8a4a;font-size:12px}
code{background:#f0f0f5;padding:1px 5px;border-radius:4px}
small{color:#777}
</style></head><body>

<h1>NQ Mean-Reversion — Backtest Presentation</h1>
<p class="sub">Ruleset <b>${RULESET.meta.name} v${RULESET.meta.version}</b> · ${meta.days} trading days (${meta.from} → ${meta.to}) · ${meta.bars.toLocaleString()} × 5-min bars · Yahoo NQ=F · generated ${new Date().toISOString().slice(0, 10)}</p>

<div class="box warn"><b>⚠️ Read this first.</b> This is ~${meta.days} trading days of one instrument — a <b>stronger sanity check than the old 11-day sample, but NOT a multi-year, multi-regime validation.</b> A few months can flatter or punish any strategy by luck of regime. Treat the numbers as directional. Real go/no-go needs years of data (TradingView or a paid feed) and out-of-sample testing. ${RULESET.known_limitations.day_trading_blind_spots}</div>

<h2>How it trades (from the ruleset)</h2>
<div class="box">
<b>Edge:</b> fade a stretched move back to the mean, on the reclaim. <br>
<b>Long:</b> ${ENTRY.long.stretch_condition}, then ${ENTRY.long.trigger}. <b>Short:</b> mirror.<br>
<b>Filters:</b> only when RANGING (<code>ADX&lt;25</code>), aligned with trend (<code>close vs EMA200</code>), during RTH (09:30–16:00 ET), flat by EOD.<br>
<b>Target:</b> the mean (BB basis). <b>Stop:</b> v1.1 = <code>1.0×ATR</code> (floats); v1.2 = <code>min(1.0×ATR, 12pt)</code> (hard cap).
</div>

<h2>Headline results (per 1 MNQ / 1 NQ)</h2>
<table>
<tr><th>Variant</th><th>Trades</th><th>Win%</th><th>PF</th><th>Net /MNQ</th><th>Net /NQ</th><th>Worst trade /MNQ</th><th>Max DD (pts)</th></tr>
<tr><td>v1.1 (floating ATR stop) — LIVE</td><td>${v11.n}</td><td>${f(v11.winRate, 0)}%</td><td>${v11.pf === Infinity ? "∞" : f(v11.pf)}</td><td class="${v11.netPts >= 0 ? "win" : "lose"}">${money(v11.netPts * PV.MNQ)}</td><td>${money(v11.netPts * PV.NQ)}</td><td>${money(v11.worstPts * PV.MNQ)}</td><td>${f(v11.maxDDpts, 0)}</td></tr>
<tr><td>v1.2 candidate (12pt hard cap)</td><td>${v12.n}</td><td>${f(v12.winRate, 0)}%</td><td>${v12.pf === Infinity ? "∞" : f(v12.pf)}</td><td class="${v12.netPts >= 0 ? "win" : "lose"}">${money(v12.netPts * PV.MNQ)}</td><td>${money(v12.netPts * PV.NQ)}</td><td>${money(v12.worstPts * PV.MNQ)} <span class=cap>(capped)</span></td><td>${f(v12.maxDDpts, 0)}</td></tr>
</table>

<h2>Sizing & Combine survival ($50K: $3,000 target · $1,000 daily · $2,000 trailing MLL)</h2>
<table>
<tr><th>Variant</th><th>Size</th><th>Net (sample)</th><th>Worst trade</th><th>Worst day</th><th>Daily-limit OK?</th><th>MLL used (worst day)</th><th>~Days to $3k</th></tr>
${sizingRows(v11, "v1.1", false)}
${sizingRows(v12, "v1.2", true)}
</table>
<p><small>Tail-risk note — v1.1's biggest stop actually placed this sample: ${f(v11.maxStopPts, 1)}pt = ${money(v11.maxStopPts * PV.MNQ * 5)} at 5 MNQ (floats with volatility, no ceiling). v1.2 hard-caps every stop at 12pt.</small></p>

<h2>Verdict</h2>
<div class="box verdict">
${meta.verdict}
</div>

<h2>What day trading hides (your point)</h2>
<div class="box">A 5-minute technical model like this is blind to the things that actually move price: scheduled macro (CPI, FOMC, NFP, jobless claims), overnight gaps, auction/liquidity dynamics, and cross-asset shocks. It only has an edge <i>inside a calm range day</i> — which is exactly why the ADX filter and RTH-only / flat-by-EOD rules exist (to sit out the regimes it can't read). It is a tactical timing tool, not a market thesis. Position size and the news calendar will protect your account far more than any parameter tweak.</div>

<p><small>Data-only backtest · no orders placed · TopStep-compliant · conservative exit ties (stop-first) · one position at a time · flat by EOD.</small></p>
</body></html>`;
}

// --- main --------------------------------------------------------------
(async () => {
  const useCache = process.argv.includes("--cache");
  let bars = await getBars(useCache);

  // --days N : keep only the most recent N TRADING days (whole days, in order).
  const dArg = process.argv.find((a) => a.startsWith("--days"));
  if (dArg) {
    const wantDays = parseInt(dArg.split("=")[1] || process.argv[process.argv.indexOf(dArg) + 1], 10);
    if (wantDays > 0) {
      const allKeys = [...new Set(bars.map((b) => dayKeyOf(b.t)))];
      const keep = new Set(allKeys.slice(-wantDays));
      bars = bars.filter((b) => keep.has(dayKeyOf(b.t)));
    }
  }

  const days = new Set(bars.map((b) => dayKeyOf(b.t))).size;
  const from = etDate(bars[0].t), to = etDate(bars[bars.length - 1].t);

  const v11 = runVariant(bars, null);
  const v12 = runVariant(bars, RULESET.variants["v1.2_candidate"].hard_stop_cap_pts);

  // build a one-paragraph verdict from the numbers
  const s11_3 = scale(v11, 3), s12_5 = scale(v12, 5);
  const v12Better = v12.netPts >= v11.netPts * 0.8 && v12.maxDDpts <= v11.maxDDpts;
  const profitable = v11.netPts > 0;
  const verdict = !profitable
    ? `Over ~${days} trading days the live <b>v1.1 is net ${money(v11.netPts * PV.MNQ)}/MNQ</b> — the edge did NOT hold up on this larger sample. This is exactly why we don't deploy on small windows. Do not size up; re-examine the strategy or test more history before risking Combine fees.`
    : `Over ~${days} trading days v1.1 nets <b>${money(v11.netPts * PV.MNQ)}/MNQ</b> (win ${f(v11.winRate, 0)}%, PF ${f(v11.pf)}). ${v12Better ? "The 12pt hard cap (v1.2) holds net while cutting drawdown and capping worst-trade risk — it remains the better profile for sizing up." : "The 12pt cap trades some net for much smaller, capped losses."} Safe path: <b>v1.1 at 1–3 MNQ</b> now (3 MNQ worst day ${money(s11_3.worstDay)}); <b>5 MNQ only with the v1.2 cap</b> (worst day ${money(s12_5.worstDay)}, ${f(s12_5.mllPctWorstDay, 0)}% of MLL). Still — confirm on years of data before going live.`;

  const html = buildReport({ days, from, to, bars: bars.length, verdict }, v11, v12);
  fs.writeFileSync(REPORT_FILE, html);

  console.log(`\nNQ Mean-Reversion backtest — ${days} trading days (${from} → ${to}), ${bars.length} bars\n`);
  const row = (lbl, r) => console.log(`${lbl.padEnd(22)} ${String(r.n).padStart(3)} tr  win ${f(r.winRate, 0).padStart(3)}%  PF ${(r.pf === Infinity ? "inf" : f(r.pf)).padStart(5)}  net/MNQ ${money(r.netPts * PV.MNQ).padStart(9)}  net/NQ ${money(r.netPts * PV.NQ).padStart(10)}  maxDD ${f(r.maxDDpts, 0)}pt  worst-trade ${money(r.worstPts * PV.MNQ)}`);
  row("v1.1 (live, floating)", v11);
  row("v1.2 (12pt cap)", v12);
  console.log(`\nReport written: ${REPORT_FILE}`);
  console.log(`Data cached:    ${DATA_FILE}`);
})().catch((e) => { console.error("engine error:", e.message); process.exit(1); });
