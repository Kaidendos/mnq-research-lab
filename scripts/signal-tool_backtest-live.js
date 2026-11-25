// =============================================================
//  backtest-live.js — honest backtest of the CURRENT LIVE strategy.
//
//  (The older backtest.js tests an abandoned v5 Pine strategy — left intact.)
//
//  Reuses lab-new4.js's buildAll() + runLedger()/tally() so there is ZERO
//  strategy reimplementation drift. Applies the EXACT live gate:
//      powerHour signal  AND  ADX(14) > 20  AND  entry 15:00–15:45 ET,
//  flat by 16:00 ET — identical to live-signal.js (lines 139–142 / 223).
//
//  Writes logs/backtest.json (read by dashboard.js's 🧪 Backtest section)
//  and prints a console report.
//
//  Run:   node backtest-live.js [lookbackDays] [sweep]
//         node backtest-live.js 60          # 60 days, ADX>20 (the live gate)
//         node backtest-live.js 60 sweep    # also sweep ADX 10..30 (exploratory)
// =============================================================
"use strict";

require("./public/indicators.js"); // populates globalThis.Indicators
const fs = require("fs");
const path = require("path");
const PX = require("./projectx");
const Lab = require("./lab-new4");
const I = globalThis.Indicators;

const PV = 2;                       // MNQ $/pt
const CONTRACTS = 5;                // live size, for $ context
const ADX_GATE = 20;                // the LIVE gate
const PH_START = 900, PH_END = 945; // 15:00–15:45 ET entry window (matches live)
const OUT = path.join(__dirname, "logs", "backtest.json");

// Build the gated signal array exactly like the live engine does.
function gatedSignals(bars, adxGate) {
  const high = bars.map((b) => b.h), low = bars.map((b) => b.l), close = bars.map((b) => b.c);
  const adx = I.dmi(high, low, close, 14, 14).adx;
  const raw = Lab.buildAll(bars).powerHour;
  const gated = new Array(bars.length);
  for (let i = 0; i < bars.length; i++) {
    const mins = Lab.etParts(bars[i].t).mins;
    if (raw[i] && adx[i] != null && adx[i] > adxGate && mins >= PH_START && mins <= PH_END) gated[i] = raw[i];
  }
  return gated;
}

function backtestOnce(bars, adxGate) {
  const t = Lab.tally(Lab.runLedger(bars, gatedSignals(bars, adxGate)));
  return {
    adxGate, n: t.n,
    winRate: t.n ? Math.round(t.winRate * 10) / 10 : null,
    pf: t.pf === Infinity ? "inf" : Math.round(t.pf * 100) / 100,
    netPts: Math.round(t.netPts * 10) / 10,
    ddPts: Math.round(t.ddPts * 10) / 10,
    worstDayPts: Math.round(t.worstDayPts * 10) / 10,
    maxLossStreak: t.maxLossStreak,
    expectancyPts: t.n ? Math.round((t.netPts / t.n) * 100) / 100 : null,
  };
}

async function main() {
  const lookbackDays = parseInt(process.argv[2] || "30", 10);
  const sweep = (process.argv[3] || "").toLowerCase() === "sweep";

  console.log(`Fetching ~${lookbackDays} days of 5m MNQ bars from ProjectX…`);
  const bars = (await PX.fetchBars({ unitNumber: 5, lookbackDays }))
    .filter((b) => b && isFinite(b.c)).sort((a, b) => a.t - b.t);
  if (bars.length < 250) { console.error(`Only ${bars.length} bars — need more history.`); process.exit(1); }
  const from = new Date(bars[0].t * 1000).toISOString().slice(0, 10);
  const to = new Date(bars[bars.length - 1].t * 1000).toISOString().slice(0, 10);
  console.log(`Loaded ${bars.length} bars  ${from} → ${to}\n`);

  if (sweep) {
    console.log("ADX gate sweep (exploratory — do NOT curve-fit; live is locked at ADX>20):");
    const hdr = "Gate".padStart(5) + "Trd".padStart(5) + "Win%".padStart(7) + "PF".padStart(7) +
      "NetPts".padStart(9) + "Net@5".padStart(10) + "MaxDD".padStart(8) + "WrstDay".padStart(9) + "ExpPts".padStart(8);
    console.log(hdr); console.log("-".repeat(hdr.length));
    for (let g = 10; g <= 30; g += 2) {
      const r = backtestOnce(bars, g);
      const net5 = r.netPts * PV * CONTRACTS;
      console.log(String(g).padStart(5) + String(r.n).padStart(5) + ((r.winRate ?? "—") + "%").padStart(7) +
        String(r.pf).padStart(7) + r.netPts.toFixed(1).padStart(9) +
        ((net5 >= 0 ? "+$" : "-$") + Math.abs(net5).toFixed(0)).padStart(10) +
        r.ddPts.toFixed(1).padStart(8) + r.worstDayPts.toFixed(1).padStart(9) +
        String(r.expectancyPts ?? "—").padStart(8));
    }
    console.log("");
  }

  // Canonical run = the live gate (ADX>20). This is what the dashboard shows.
  const r = backtestOnce(bars, ADX_GATE);
  const payload = { generatedAt: new Date().toISOString(), from, to, bars: bars.length, ...r };
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(payload, null, 2));

  const net5 = r.netPts * PV * CONTRACTS;
  console.log(`=== Live strategy backtest (ADX>${ADX_GATE}, ${from}→${to}) ===`);
  console.log(`Trades:          ${r.n}`);
  console.log(`Win rate:        ${r.winRate}%`);
  console.log(`Profit factor:   ${r.pf}`);
  console.log(`Net points:      ${r.netPts}   (= ${net5 >= 0 ? "+$" : "-$"}${Math.abs(net5).toFixed(0)} @ ${CONTRACTS} MNQ)`);
  console.log(`Max drawdown:    ${r.ddPts} pts   (= $${(r.ddPts * PV * CONTRACTS).toFixed(0)} @ ${CONTRACTS} MNQ vs $2,000 MLL)`);
  console.log(`Worst day:       ${r.worstDayPts} pts   (= $${(Math.abs(r.worstDayPts) * PV * CONTRACTS).toFixed(0)} @ ${CONTRACTS} MNQ vs $1,000 DLL)`);
  console.log(`Max loss streak: ${r.maxLossStreak}`);
  console.log(`Expectancy:      ${r.expectancyPts} pts/trade`);
  console.log(`\nWrote ${OUT} — the dashboard's 🧪 Backtest section will show this.`);
}

main().catch((e) => { console.error("backtest error:", e.stack || e.message); process.exit(1); });
