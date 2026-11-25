// =============================================================
//  champion90.js — the LOCKED CHAMPION on the full ~90-day chart.
//
//  "The best one" from the catalog13 screen = the champion: power-hour signal
//  GATED by ADX(14)>20, EMA200 trend + close trigger (all inside lab-new4's
//  powerHour build), entry 15:00-15:45 ET, flat by 16:00, bracket 1.2/1.8 ATR.
//
//  This applies the EXACT live gate from backtest-live.js (powerHour AND adx>20)
//  — zero strategy reimplementation — but against the 89-day TradingView MNQ 5m
//  export (back to Mar 8) instead of the ProjectX fetch, and it does NOT
//  overwrite logs/backtest.json (the locked 12-day dashboard record stays put).
//
//  Cousin note: power-hour-90d.js runs the UN-gated powerHour (#42). This is the
//  ADX>20-gated CHAMPION (#7 in catalog13) — the actual locked strategy.
//
//  DATA-ONLY / TopStep-compliant: reads a local CSV, never places an order.
//  Run:  node champion90.js ["path\to\90d.csv"]
// =============================================================
"use strict";

require("./public/indicators.js");
const fs = require("fs");
const path = require("path");
const Lab = require("./lab-new4");
const I = globalThis.Indicators;

const CSV_90 = process.argv[2] || "C:\\Users\\kaide\\Downloads\\CME_MINI_DL_MNQ1!, 5 (1).csv";
const ADX_GATE = 20, PH_START = 900, PH_END = 945;
const PV5 = 10, PV1 = 2;                 // $/pt at 5 MNQ (live size) and 1 MNQ
const DLL = Lab.DLL, MLL = Lab.MLL, TARGET = 3000;
const OUT_MD = path.join(__dirname, "logs", "champion90-report.md");
const f = (x, d = 0) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));
const money = (x) => (x >= 0 ? "+$" : "-$") + f(Math.abs(x));

// EXACT live champion gate (identical to backtest-live.js:gatedSignals).
function championSignals(bars) {
  const high = bars.map((b) => b.h), low = bars.map((b) => b.l), close = bars.map((b) => b.c);
  const adx = I.dmi(high, low, close, 14, 14).adx;
  const raw = Lab.buildAll(bars).powerHour;
  const gated = new Array(bars.length);
  for (let i = 0; i < bars.length; i++) {
    const mins = Lab.etParts(bars[i].t).mins;
    if (raw[i] && adx[i] != null && adx[i] > ADX_GATE && mins >= PH_START && mins <= PH_END) gated[i] = raw[i];
  }
  return gated;
}

// chronological $50K Combine sim (same rules as power-hour-90d.js)
function simulate(days, size) {
  let realized = 0, peak = 0, passDayIdx = null;
  for (let d = 0; d < days.length; d++) {
    let dayPnL = 0;
    for (const pts of days[d]) {
      const pnl = pts * size * PV1; realized += pnl; dayPnL += pnl;
      if (realized > peak) peak = realized;
      const floor = Math.min(peak - MLL, 0);
      if (realized <= floor) return { outcome: "MLL", profit: realized, peak, passDayIdx };
      if (dayPnL <= -DLL) return { outcome: "DLL", profit: realized, peak, passDayIdx };
      if (realized >= TARGET && passDayIdx == null) { passDayIdx = d; return { outcome: "PASS", profit: realized, peak, passDayIdx }; }
    }
  }
  return { outcome: "INCOMPLETE", profit: realized, peak, passDayIdx };
}
function mulberry32(a) { return function () { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function shuffled(arr, rng) { const a = arr.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rng() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }

(function () {
  const bars = Lab.loadCsv(CSV_90);
  const dayKeys = [...new Set(bars.map((b) => Lab.dayKeyOf(b.t)))];
  const sig = championSignals(bars);
  const r = Lab.tally(Lab.runLedger(bars, sig));
  const span = [bars[0].t, bars[bars.length - 1].t].map((s) => new Date(s * 1000).toISOString().slice(0, 10));

  const net5 = r.netPts * PV5, net1 = r.netPts * PV1;
  const dd5 = r.ddPts * PV5, wd5 = Math.abs(r.worstDayPts) * PV5;

  console.log(`CHAMPION (Power-Hour + ADX>20, EMA200 trend) — FULL ~90-DAY CHART`);
  console.log(`Source: ${path.basename(CSV_90)}`);
  console.log(`Span: ${span[0]} -> ${span[1]}  |  ${dayKeys.length} ET trading days  |  ${bars.length} bars\n`);

  console.log(`(1) OVERALL EDGE`);
  console.log(`  Trades ${r.n}   Win% ${f(r.winRate, 1)}   PF ${f(r.pf, 2)}   MaxLossStreak ${r.maxLossStreak}   Exp ${f(r.netPts / (r.n || 1), 2)} pts/trd`);
  console.log(`  Net:       ${money(net5)} @5 MNQ    ${money(net1)} @1 MNQ`);
  console.log(`  MaxDD:     ${money(-dd5)} @5 MNQ   (vs $${MLL} trailing MLL)   ${dd5 >= MLL ? "MLL BREACH!" : "ok"}`);
  console.log(`  WorstDay:  ${money(-wd5)} @5 MNQ   (vs $${DLL} daily DLL)      ${wd5 >= DLL ? "DLL BREACH!" : "ok"}`);
  console.log(`  Combine-feasible @5 MNQ (worstDay<$1000 AND maxDD<$2000): ${(wd5 < DLL && dd5 < MLL) ? "YES" : "NO"}`);
  console.log(`  Reference baselines — 13d: +$8,154 (10t, 80%) | 58d: +$13,540 (50t, 66%, PF 3.15) @5 MNQ.\n`);

  // chronological Combine + return-order stress at live size (5 MNQ)
  const ledger = Lab.runLedger(bars, sig);
  const dayMap = new Map();
  for (const t of ledger) { if (!dayMap.has(t.date)) dayMap.set(t.date, []); dayMap.get(t.date).push(t.pts); }
  const days = [...dayMap.values()];
  console.log(`(2) $50K COMBINE — ${ledger.length} trades over ${days.length} active days. Pass +$${TARGET}, DLL $${DLL}/day, MLL $${MLL} trailing.`);
  const chrono = simulate(days, 5);
  console.log(`  REAL ORDER, flat 5 MNQ -> ${chrono.outcome}   final ${money(chrono.profit)}   peak ${money(chrono.peak)}${chrono.passDayIdx == null ? "" : "   passed on active day #" + (chrono.passDayIdx + 1)}`);
  const N = 10000, rng = mulberry32(12345);
  let pass = 0, mll = 0, dll = 0, inc = 0; const pd = [];
  for (let n = 0; n < N; n++) { const sr = simulate(shuffled(days, rng), 5); if (sr.outcome === "PASS") { pass++; pd.push(sr.passDayIdx + 1); } else if (sr.outcome === "MLL") mll++; else if (sr.outcome === "DLL") dll++; else inc++; }
  pd.sort((a, b) => a - b); const med = pd.length ? pd[Math.floor(pd.length / 2)] : null;
  console.log(`  RETURN-ORDER STRESS (${N} shuffles, flat 5 MNQ): PASS ${f(pass / N * 100, 1)}%  Fail-MLL ${f(mll / N * 100, 1)}%  Fail-DLL ${f(dll / N * 100, 1)}%  NoPass ${f(inc / N * 100, 1)}%  MedPassDay ${med == null ? "—" : "#" + med}`);

  const md = [
    `# Champion on the ~90-day chart (${new Date().toISOString().slice(0, 10)})`,
    ``,
    `Locked champion (Power-Hour + ADX>20 + EMA200 trend, 1.2/1.8 ATR bracket, flat 16:00) on the 89-day TradingView MNQ 5m export. EXACT live gate from backtest-live.js. Dollars @5 MNQ (live size).`,
    ``,
    `- **Span:** ${span[0]} → ${span[1]} (${dayKeys.length} ET days, ${bars.length} bars)`,
    `- **Trades:** ${r.n}  |  **Win%:** ${f(r.winRate, 1)}  |  **PF:** ${f(r.pf, 2)}  |  **Max loss streak:** ${r.maxLossStreak}`,
    `- **Net:** ${money(net5)} @5 MNQ (${money(net1)} @1 MNQ)`,
    `- **Max drawdown:** ${money(-dd5)} @5 MNQ vs $${MLL} MLL — ${dd5 >= MLL ? "**BREACH**" : "ok"}`,
    `- **Worst day:** ${money(-wd5)} @5 MNQ vs $${DLL} DLL — ${wd5 >= DLL ? "**BREACH**" : "ok"}`,
    `- **Combine-feasible @5 MNQ:** ${(wd5 < DLL && dd5 < MLL) ? "YES" : "NO"}`,
    `- **Chronological Combine, flat 5 MNQ:** ${chrono.outcome}, final ${money(chrono.profit)}${chrono.passDayIdx == null ? "" : " (passed active day #" + (chrono.passDayIdx + 1) + ")"}`,
    `- **Return-order stress (10k shuffles, 5 MNQ):** PASS ${f(pass / N * 100, 1)}% / Fail-MLL ${f(mll / N * 100, 1)}% / Fail-DLL ${f(dll / N * 100, 1)}% / NoPass ${f(inc / N * 100, 1)}%, median pass day #${med ?? "—"}`,
    ``,
    `Baselines for comparison: 13d +$8,154 (10t, 80%); 58d +$13,540 (50t, 66%, PF 3.15) @5 MNQ.`,
    `Gross only (no slippage/commissions). DATA-ONLY: live bot, champion.json, and logs/backtest.json untouched.`,
    ``,
  ];
  fs.writeFileSync(OUT_MD, md.join("\n"));
  console.log(`\nSaved ${OUT_MD}. DATA-ONLY: champion.json + logs/backtest.json untouched.`);
})();
