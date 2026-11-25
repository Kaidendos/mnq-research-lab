// =============================================================
//  optimize.js — overnight strategy search + optimizer.
//
//  Saves nothing about the LIVE bot. It is a research tool: it sweeps ~210
//  parameter configurations across 10 strategy families, backtests each on
//  the available historical charts, scores them for ROBUSTNESS (not just raw
//  net), and writes a ranked report. The current live strategy (the locked
//  "champion", strategies/champion.json) is included as one of the candidates
//  so we can see exactly where it lands in the field.
//
//  Exit model is REUSED verbatim from lab-new4.js (runLedger/tally/etParts):
//  RTH entries, flat by 16:00 ET, one position at a time, stop-first on ties,
//  mark-to-close at session end. So there is zero exit-logic drift between
//  this optimizer, the 50-strategy lab, and backtest-live.js.
//
//  Samples:
//    A = data/nq-5m.json   (cached NQ=F 5m, ~50 trading days) — PRIMARY, deterministic.
//    B = ProjectX MNQ 5m   (the real traded instrument, ~60d) — fetched live if reachable.
//  A candidate must hold up on BOTH to make the robust shortlist.
//
//  DATA-ONLY / TopStep-compliant: reads local + public data, never places an order.
//
//  Run:  node optimize.js
// =============================================================
"use strict";

const fs = require("fs");
const path = require("path");
require("./public/indicators.js");
const I = globalThis.Indicators;
const Lab = require("./lab-new4");        // reuse exact exit model + ET helpers
const PX = require("./projectx");

const PV = 2, CONTRACTS = 5, DPP = PV * CONTRACTS; // $/pt at live size = 10
const DLL = 1000, MLL = 2000;             // Combine $50K limits
const OUT_JSON = path.join(__dirname, "logs", "optimization-results.json");
const OUT_MD = path.join(__dirname, "logs", "optimization-report.md");

// ---------------- precompute indicators once per sample ----------------
function sessionVWAP(bars) {
  const vwap = new Array(bars.length).fill(null), sd = new Array(bars.length).fill(null);
  let cur = null, vNum = 0, vDen = 0, vNum2 = 0;
  for (let i = 0; i < bars.length; i++) {
    const p = Lab.etParts(bars[i].t);
    if (p.k !== cur) { cur = p.k; vNum = vDen = vNum2 = 0; }
    if (p.mins >= 570 && p.mins < 960) { const hlc3 = (bars[i].h + bars[i].l + bars[i].c) / 3, v = bars[i].v || 1; vNum += hlc3 * v; vNum2 += hlc3 * hlc3 * v; vDen += v; }
    if (vDen > 0) { const m = vNum / vDen; vwap[i] = m; sd[i] = Math.sqrt(Math.max(0, vNum2 / vDen - m * m)); }
  }
  return { vwap, sd };
}
function rollPrior(high, low, n) {
  const hi = new Array(high.length).fill(null), lo = new Array(high.length).fill(null);
  for (let i = n; i < high.length; i++) { let mx = -Infinity, mn = Infinity; for (let k = i - n; k < i; k++) { mx = Math.max(mx, high[k]); mn = Math.min(mn, low[k]); } hi[i] = mx; lo[i] = mn; }
  return { hi, lo };
}
function buildCtx(bars) {
  const close = bars.map((b) => b.c), high = bars.map((b) => b.h), low = bars.map((b) => b.l), open = bars.map((b) => b.o);
  const N = bars.length;
  const atr = I.atr(high, low, close, 14);
  const ema200 = I.ema(close, 200), ema21 = I.ema(close, 21);
  const sma20 = I.sma(close, 20), dev = I.stdev(close, 20);
  const upBB = sma20.map((v, k) => v == null ? null : v + 2 * dev[k]);
  const loBB = sma20.map((v, k) => v == null ? null : v - 2 * dev[k]);
  const rsi2 = I.rsi(close, 2), rsi14 = I.rsi(close, 14);
  const { macdLine } = I.macd(close, 12, 26, 9);
  const zeros = macdLine.map(() => 0);
  const xUp = I.crossover(macdLine, zeros), xDn = I.crossunder(macdLine, zeros);
  const d = I.dmi(high, low, close, 14, 14);
  const { vwap, sd } = sessionVWAP(bars);
  const don20 = rollPrior(high, low, 20), don55 = rollPrior(high, low, 55);
  const mins = bars.map((b) => Lab.etParts(b.t).mins);
  return { bars, close, high, low, open, N, atr, ema200, ema21, sma20, dev, upBB, loBB, rsi2, rsi14, xUp, xDn, adx: d.adx, vwap, sd, don20, don55, mins };
}

// ---------------- trigger families: return 1 (long) / -1 (short) / 0 ----------------
function adxOk(c, i, gate) { return !gate || (c.adx[i] != null && c.adx[i] > gate); }
const TRIG = {
  powerHour(c, i, cand) {
    const m = c.mins[i]; if (m < cand.win[0] || m > cand.win[1]) return 0;
    if (c.ema200[i] == null || !adxOk(c, i, cand.adxGate)) return 0;
    if (c.close[i] > c.ema200[i] && c.close[i] > c.open[i] && c.close[i] > c.close[i - 1]) return 1;
    if (c.close[i] < c.ema200[i] && c.close[i] < c.open[i] && c.close[i] < c.close[i - 1]) return -1;
    return 0;
  },
  emaSlope(c, i, cand) {
    if (c.ema21[i] == null || c.ema21[i - 3] == null || c.ema200[i] == null || c.atr[i] == null || !adxOk(c, i, cand.adxGate)) return 0;
    const sl = (c.ema21[i] - c.ema21[i - 3]) / 3;
    if (c.close[i] > c.ema200[i] && sl > 0.1 * c.atr[i] && c.close[i] > c.open[i]) return 1;
    if (c.close[i] < c.ema200[i] && sl < -0.1 * c.atr[i] && c.close[i] < c.open[i]) return -1;
    return 0;
  },
  macdZero(c, i, cand) {
    if (c.ema200[i] == null || !adxOk(c, i, cand.adxGate)) return 0;
    if (c.close[i] > c.ema200[i] && c.xUp[i]) return 1;
    if (c.close[i] < c.ema200[i] && c.xDn[i]) return -1;
    return 0;
  },
  don20(c, i, cand) {
    if (c.don20.hi[i] == null || !adxOk(c, i, cand.adxGate)) return 0;
    if (c.close[i - 1] <= c.don20.hi[i] && c.close[i] > c.don20.hi[i]) return 1;
    if (c.close[i - 1] >= c.don20.lo[i] && c.close[i] < c.don20.lo[i]) return -1;
    return 0;
  },
  don55(c, i, cand) {
    if (c.don55.hi[i] == null || !adxOk(c, i, cand.adxGate)) return 0;
    if (c.close[i - 1] <= c.don55.hi[i] && c.close[i] > c.don55.hi[i]) return 1;
    if (c.close[i - 1] >= c.don55.lo[i] && c.close[i] < c.don55.lo[i]) return -1;
    return 0;
  },
  consec3(c, i, cand) {
    if (!adxOk(c, i, cand.adxGate)) return 0;
    if (c.close[i] > c.close[i - 1] && c.close[i - 1] > c.close[i - 2] && c.close[i - 2] > c.close[i - 3]) return 1;
    if (c.close[i] < c.close[i - 1] && c.close[i - 1] < c.close[i - 2] && c.close[i - 2] < c.close[i - 3]) return -1;
    return 0;
  },
  rsi2(c, i) { if (c.rsi2[i] == null) return 0; if (c.rsi2[i] < 10) return 1; if (c.rsi2[i] > 90) return -1; return 0; },
  vwapFade(c, i) { if (c.vwap[i] == null || !(c.sd[i] > 0)) return 0; const z = (c.close[i] - c.vwap[i]) / c.sd[i]; if (z <= -2 && c.close[i] > c.open[i]) return 1; if (z >= 2 && c.close[i] < c.open[i]) return -1; return 0; },
  bbFade(c, i) { if (c.loBB[i] == null) return 0; if (c.low[i] <= c.loBB[i] && c.close[i] > c.open[i]) return 1; if (c.high[i] >= c.upBB[i] && c.close[i] < c.open[i]) return -1; return 0; },
  zscore(c, i) { if (c.sma20[i] == null || !(c.dev[i] > 0)) return 0; const z = (c.close[i] - c.sma20[i]) / c.dev[i]; if (z < -2) return 1; if (z > 2) return -1; return 0; },
};

function buildSig(c, cand) {
  const fn = TRIG[cand.family], sig = new Array(c.N).fill(null);
  for (let i = 8; i < c.N; i++) {
    const a = c.atr[i]; if (a == null) continue;
    const dir = fn(c, i, cand); if (!dir) continue;
    const e = c.close[i];
    sig[i] = dir === 1
      ? { dir: 1, entry: e, stop: e - cand.stop * a, target: e + cand.target * a }
      : { dir: -1, entry: e, stop: e + cand.stop * a, target: e - cand.target * a };
  }
  return sig;
}

function evalSample(c, cand) {
  const t = Lab.tally(Lab.runLedger(c.bars, buildSig(c, cand)));
  const pf = t.pf === Infinity ? 99 : Math.round(t.pf * 100) / 100;
  return {
    n: t.n, win: t.n ? Math.round(t.winRate * 10) / 10 : 0, pf,
    net: Math.round(t.netPts * 10) / 10, dd: Math.round(t.ddPts * 10) / 10,
    wd: Math.round(t.worstDayPts * 10) / 10, mls: t.maxLossStreak,
    exp: t.n ? Math.round((t.netPts / t.n) * 100) / 100 : 0,
    feasible: Math.abs(t.worstDayPts) * DPP < DLL && t.ddPts * DPP < MLL,
  };
}

// Composite score: rewards net on BOTH samples, demands Combine feasibility,
// penalizes drawdown, and discounts anything that fails out-of-sample.
function score(A, B) {
  if (A.n < 8) return -1e9;
  let base = A.net, rob;
  if (B) { base += B.net; rob = (B.net > 0 && B.pf >= 1.2) ? 1.0 : 0.5; }
  else rob = 0.8;
  const feas = A.feasible ? 1 : 0.4;
  const ddPen = 0.25 * A.dd + (B ? 0.25 * B.dd : 0);
  return Math.round((base * rob * feas - ddPen) * 10) / 10;
}

// ---------------- candidate grid (~210 configs across 10 families) ----------------
function buildCandidates() {
  const cands = []; let id = 0;
  // Champion family — deep sweep of window / stop / target / ADX gate.
  for (const win of [[900, 945], [900, 960], [840, 960], [870, 945]])
    for (const stop of [1.0, 1.2, 1.5])
      for (const target of [1.8, 2.4, 3.0])
        for (const adxGate of [20, 25])
          cands.push({ id: id++, family: "powerHour", win, stop, target, adxGate, label: `PH ${win[0]}-${win[1]} s${stop} t${target} adx${adxGate}` });
  // Other momentum/breakout families.
  for (const family of ["emaSlope", "macdZero", "don20", "don55", "consec3"])
    for (const stop of [1.0, 1.5, 2.0])
      for (const target of [1.5, 2.0, 3.0])
        for (const adxGate of [0, 20])
          cands.push({ id: id++, family, win: [570, 960], stop, target, adxGate, label: `${family} s${stop} t${target} adx${adxGate || "off"}` });
  // Mean-reversion / fade families (no trend/ADX gate, tighter targets).
  for (const family of ["rsi2", "vwapFade", "bbFade", "zscore"])
    for (const stop of [1.0, 1.5, 2.0])
      for (const target of [1.0, 1.5, 2.0, 2.5])
        cands.push({ id: id++, family, win: [570, 960], stop, target, adxGate: 0, label: `${family} s${stop} t${target}` });
  return cands;
}
const isChampion = (c) => c.family === "powerHour" && c.win[0] === 900 && c.win[1] === 945 && c.stop === 1.2 && c.target === 1.8 && c.adxGate === 20;

// ---------------- formatting ----------------
const dol = (pts) => (pts >= 0 ? "+$" : "-$") + Math.abs(pts * DPP).toFixed(0);
function row(r) {
  const A = r.A, B = r.B;
  return String(r.rank).padStart(4) + "  " + r.label.padEnd(30) +
    String(A.n).padStart(4) + (A.win + "%").padStart(7) + String(A.pf).padStart(7) + dol(A.net).padStart(9) +
    (B ? (String(B.n).padStart(4) + String(B.pf).padStart(6) + dol(B.net).padStart(9)) : "    —     —        —") +
    String(r.score).padStart(9) + (A.feasible ? "  ok" : "  DD!") + (isChampion(r.cand) ? "  <<< CHAMPION" : "");
}

// Load both samples (A = cached NQ 5m, B = ProjectX MNQ best-effort) with logging.
async function loadSamples() {
  const barsA = JSON.parse(fs.readFileSync(path.join(__dirname, "data", "nq-5m.json"), "utf8"))
    .filter((b) => b && isFinite(b.c)).sort((a, b) => a.t - b.t);
  const spanA = [barsA[0].t, barsA[barsA.length - 1].t].map((s) => new Date(s * 1000).toISOString().slice(0, 10));
  const daysA = new Set(barsA.map((b) => Lab.dayKeyOf(b.t))).size;
  console.log(`Sample A (cached NQ=F 5m): ${barsA.length} bars, ${daysA} days, ${spanA[0]} -> ${spanA[1]}`);
  let barsB = null, spanB = null, daysB = 0;
  try {
    const raw = await PX.fetchBars({ unitNumber: 5, lookbackDays: 60 });
    const b = raw.filter((x) => x && isFinite(x.c)).sort((a, b) => a.t - b.t);
    if (b.length >= 250) { barsB = b; spanB = [b[0].t, b[b.length - 1].t].map((s) => new Date(s * 1000).toISOString().slice(0, 10)); daysB = new Set(b.map((x) => Lab.dayKeyOf(x.t))).size; }
  } catch (e) { console.log(`Sample B (ProjectX MNQ): unavailable (${e.message}); scoring on Sample A only.`); }
  if (barsB) console.log(`Sample B (ProjectX MNQ 5m): ${barsB.length} bars, ${daysB} days, ${spanB[0]} -> ${spanB[1]}`);
  return { barsA, spanA, daysA, barsB, spanB, daysB };
}

// Detailed single-config report: full stats + per-trade ledger on each sample.
async function detailOne(cand) {
  const { barsA, spanA, barsB, spanB } = await loadSamples();
  console.log(`\n=== DETAIL: ${cand.label}  (family=${cand.family}, window ${cand.win[0]}-${cand.win[1]} ET, stop ${cand.stop}xATR, target ${cand.target}xATR, ADX>${cand.adxGate}) ===`);
  const samples = [["A — NQ=F 58d", barsA, spanA]];
  if (barsB) samples.push(["B — ProjectX MNQ", barsB, spanB]);
  for (const [label, bars, span] of samples) {
    const ctx = buildCtx(bars);
    const ledger = Lab.runLedger(bars, buildSig(ctx, cand));
    const m = evalSample(ctx, cand);
    console.log(`\n--- Sample ${label}  (${span[0]} -> ${span[1]}) ---`);
    console.log(`Trades ${m.n} | Win ${m.win}% | PF ${m.pf} | Net ${m.net} pts (${dol(m.net)} @5MNQ) | Expectancy ${m.exp} pts`);
    console.log(`MaxDD ${m.dd} pts ($${(m.dd * DPP).toFixed(0)} vs $2000 MLL) | Worst day ${m.wd} pts ($${(Math.abs(m.wd) * DPP).toFixed(0)} vs $1000 DLL) | Max loss streak ${m.mls} | Combine-feasible @5MNQ: ${m.feasible ? "YES" : "NO"}`);
    if (ledger.length) {
      console.log("  " + "Date".padEnd(12) + "Dir".padStart(5) + "Pts".padStart(9) + "  $@5MNQ".padStart(9) + "  Cum$");
      let cum = 0;
      for (const t of ledger) { cum += t.pts; console.log("  " + t.date.padEnd(12) + (t.dir === 1 ? "long" : "short").padStart(5) + t.pts.toFixed(2).padStart(9) + dol(t.pts).padStart(11) + ("  " + dol(cum))); }
    }
    // --- Combine survival sim (rule-agnostic facts) at 5 MNQ ($10/pt) and 1 NQ ($20/pt) ---
    for (const [tag, pv] of [["5 MNQ", 10], ["1 NQ", 20]]) {
      // per-trade running drawdown (intraday-style worst peak-to-trough)
      let tc = 0, tpk = 0, ddTrade = 0;
      for (const t of ledger) { tc += t.pts; tpk = Math.max(tpk, tc); ddTrade = Math.max(ddTrade, tpk - tc); }
      // per-day (EOD) equity curve
      const order = []; const idx = new Map();
      for (const t of ledger) { if (!idx.has(t.date)) { idx.set(t.date, order.length); order.push({ date: t.date, pts: 0 }); } order[idx.get(t.date)].pts += t.pts; }
      let c = 0, pk = 0, ddDay = 0, passDay = null, lockDay = null; const dll = [];
      for (const d of order) {
        c += d.pts; pk = Math.max(pk, c); ddDay = Math.max(ddDay, pk - c);
        if (passDay === null && c * pv >= 3000) passDay = d.date;       // +$3000 profit target reached
        if (lockDay === null && c * pv >= 2000) lockDay = d.date;       // banked +$2000 -> EOD trailing floor locks at start balance
        if (d.pts * pv <= -1000) dll.push(`${d.date}:$${Math.round(d.pts * pv)}`);
      }
      console.log(`  [${tag} @$${pv}/pt] target +$3000 on ${passDay || "NEVER"} | floor-locks(+$2000 banked) on ${lockDay || "NEVER"} | maxDD EOD $${(ddDay * pv).toFixed(0)} / per-trade $${(ddTrade * pv).toFixed(0)} vs $2000 MLL | $1000-DLL breach days: ${dll.length}${dll.length ? " (" + dll.join(", ") + ")" : ""}`);
    }
  }
  console.log(`\nReminder: this is a research read-out only — it changes nothing about the live bot. The locked champion is still ADX>20.`);
}

async function main() {
  const t0 = Date.now();
  const { barsA, spanA, daysA, barsB, spanB, daysB } = await loadSamples();
  const ctxA = buildCtx(barsA), ctxB = barsB ? buildCtx(barsB) : null;
  const cands = buildCandidates();
  console.log(`\nSweeping ${cands.length} configurations across 10 families on ${barsB ? "2 samples" : "1 sample"}…\n`);

  const results = cands.map((cand) => {
    const A = evalSample(ctxA, cand), B = ctxB ? evalSample(ctxB, cand) : null;
    return { cand, label: cand.label, family: cand.family, A, B, score: score(A, B) };
  }).sort((a, b) => b.score - a.score);
  results.forEach((r, i) => (r.rank = i + 1));

  // Robust shortlist: enough trades, profitable + PF on BOTH samples, Combine-feasible.
  const robust = results.filter((r) => r.A.n >= 12 && r.A.net > 0 && r.A.pf >= 1.5 && r.A.feasible &&
    (!r.B || (r.B.net > 0 && r.B.pf >= 1.3)));

  const champ = results.find((r) => isChampion(r.cand));

  // ---- console report ----
  const hdr = "Rank  " + "Strategy (family + params)".padEnd(30) + "  A:n".padStart(4) + "Win%".padStart(7) + "PF".padStart(7) + "Net@5".padStart(9) + "  B:n".padStart(6) + "PF".padStart(6) + "Net@5".padStart(9) + "Score".padStart(9) + "  Feas";
  console.log("TOP 25 BY ROBUST SCORE  (Net@5 = $ at 5 MNQ; A = cached NQ, B = ProjectX MNQ)");
  console.log(hdr); console.log("-".repeat(hdr.length));
  for (const r of results.slice(0, 25)) console.log(row(r));

  console.log(`\nROBUST SHORTLIST — profitable + PF>=1.5 (A) / >=1.3 (B), >=12 trades, Combine-feasible @5MNQ: ${robust.length} of ${results.length}`);
  if (robust.length) { console.log(hdr); console.log("-".repeat(hdr.length)); for (const r of robust.slice(0, 15)) console.log(row(r)); }
  else console.log("  (none cleared every gate — see caveat)");

  console.log(`\nCHAMPION (current live strategy) ranks #${champ.rank} of ${results.length}.`);
  console.log(hdr); console.log("-".repeat(hdr.length)); console.log(row(champ));

  // ---- write artifacts ----
  fs.mkdirSync(path.dirname(OUT_JSON), { recursive: true });
  fs.writeFileSync(OUT_JSON, JSON.stringify({
    generatedAt: new Date().toISOString(),
    sampleA: { src: "data/nq-5m.json", bars: barsA.length, days: daysA, from: spanA[0], to: spanA[1] },
    sampleB: barsB ? { src: "ProjectX MNQ 5m", bars: barsB.length, days: daysB, from: spanB[0], to: spanB[1] } : null,
    nConfigs: results.length, championRank: champ.rank, robustCount: robust.length,
    results: results.map((r) => ({ rank: r.rank, family: r.family, label: r.label, isChampion: isChampion(r.cand), score: r.score, A: r.A, B: r.B })),
  }, null, 2));

  const md = [];
  md.push(`# Strategy Optimization Report`, ``, `Generated: ${new Date().toISOString()}`, ``);
  md.push(`- **Sample A:** cached NQ=F 5m — ${barsA.length} bars, ${daysA} days, ${spanA[0]} → ${spanA[1]}`);
  md.push(barsB ? `- **Sample B:** ProjectX MNQ 5m — ${barsB.length} bars, ${daysB} days, ${spanB[0]} → ${spanB[1]}` : `- **Sample B:** unavailable (scored on A only)`);
  md.push(`- **Configurations tested:** ${results.length} across 10 families`);
  md.push(`- **Champion rank:** #${champ.rank} of ${results.length}`, `- **Robust shortlist size:** ${robust.length}`, ``);
  md.push(`Net@5 = dollars at 5 MNQ ($10/pt). "Feasible" = worst day < $1,000 (DLL) and max drawdown < $2,000 (MLL).`, ``);
  const mdTable = (rows) => {
    const out = ["| Rank | Strategy | A:trd | A:Win% | A:PF | A:Net@5 | B:trd | B:PF | B:Net@5 | Score | Feas |",
      "|---:|:--|---:|---:|---:|---:|---:|---:|---:|---:|:--:|"];
    for (const r of rows) out.push(`| ${r.rank}${isChampion(r.cand) ? " ⭐" : ""} | ${r.label} | ${r.A.n} | ${r.A.win}% | ${r.A.pf} | ${dol(r.A.net)} | ${r.B ? r.B.n : "—"} | ${r.B ? r.B.pf : "—"} | ${r.B ? dol(r.B.net) : "—"} | ${r.score} | ${r.A.feasible ? "ok" : "DD!"} |`);
    return out.join("\n");
  };
  md.push(`## Top 25 by robust score`, ``, mdTable(results.slice(0, 25)), ``);
  md.push(`## Robust shortlist (cleared every gate)`, ``, robust.length ? mdTable(robust.slice(0, 20)) : "_None cleared every gate._", ``);
  md.push(`## Champion (current live strategy)`, ``, mdTable([champ]), ``);
  md.push(`## Caveats`, ``,
    `- Both samples are ~2-3 months of one instrument — a single regime, not multi-year proof.`,
    `- A grid search WILL surface configs that look great by luck. The robust shortlist (must hold up on both samples) is the only output worth taking seriously, and even that needs forward/out-of-sample confirmation before it could replace the locked champion.`,
    `- Score is a ranking heuristic, not a promise. Read the raw n / PF / Net / drawdown columns.`, ``);
  fs.writeFileSync(OUT_MD, md.join("\n"));

  console.log(`\nWrote ${path.relative(__dirname, OUT_JSON)} and ${path.relative(__dirname, OUT_MD)}  (${((Date.now() - t0) / 1000).toFixed(1)}s)`);
}

// Dispatch: `node optimize.js one [stop] [target] [adx] [winStart] [winEnd]`
// runs a detailed single-config report (default = the 76% PH s1.2 t1.8 adx25).
// Anything else runs the full 210-config sweep.
function cliRun() {
  if ((process.argv[2] || "").toLowerCase() === "one") {
    const a = process.argv;
    const stop = parseFloat(a[3] || "1.2"), target = parseFloat(a[4] || "1.8"), adxGate = parseInt(a[5] || "25", 10);
    const win = [parseInt(a[6] || "900", 10), parseInt(a[7] || "945", 10)];
    return detailOne({ family: "powerHour", win, stop, target, adxGate, label: `PH ${win[0]}-${win[1]} s${stop} t${target} adx${adxGate}` });
  }
  return main();
}
cliRun().catch((e) => { console.error("optimize error:", e.stack || e.message); process.exit(1); });
