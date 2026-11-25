// =============================================================
//  power-hour-90d.js — Power-hour (#42) over the full ~90-DAY 5-minute chart.
//
//  Why this exists: every prior Power-hour test (windows, drawdown, staged) ran
//  on the 58-day Yahoo NQ=F 5m sample, because Yahoo HARD-CAPS 5-minute history
//  at ~60 days (anything past that returns HTTP 422 — re-confirmed live this run:
//  60d OK / 75d 422 / 90d 422). This script instead loads a TradingView MNQ
//  5-minute export that reaches back to MARCH 8 2026 — 89 ET trading days, the
//  stretch Yahoo could never see — and re-runs the SAME battery:
//    (1) overall edge at 5 MNQ ($10/pt) and 1 MNQ ($2/pt) + Combine flags
//    (2) 5 rolling 30-trading-day windows (consistency, not concentration)
//    (3) chronological $50K Combine sim + 10k return-order stress test
//
//  Reuses lab-new4.js's exact strategy code + exit model (imported). DATA-ONLY /
//  TopStep-compliant: reads a local CSV, never places an order.
//  Run:  node power-hour-90d.js
// =============================================================
"use strict";

const Lab = require("./lab-new4.js");

const CSV_90 = process.argv[2] || "C:\\Users\\kaide\\Downloads\\CME_MINI_DL_MNQ1!, 5 (1).csv";
const KEY = "powerHour";
const PV5 = 10, PV1 = 2, PV = 2;           // $/pt at 5 MNQ, 1 MNQ, and per-1-MNQ
const MLL = Lab.MLL, DLL = Lab.DLL, TARGET = 3000;
const f = (x, d = 0) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));
const money = (x) => (x >= 0 ? "+$" : "-$") + f(Math.abs(x));

// ET calendar date as YYYYMMDD (matches lab-new4's ET Date construction)
function etYmd(s) {
  const d = new Date(new Date(s * 1000).toLocaleString("en-US", { timeZone: "America/New_York" }));
  return d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
}
function maskToWindow(bars, sig, lo, hi) {
  return sig.map((v, i) => { if (!v) return null; const d = etYmd(bars[i].t); return d >= lo && d <= hi ? v : null; });
}

// --- Combine sim (same rules as power-hour-staged.js) ---
function simulate(days, size) {
  let realized = 0, peak = 0, passDayIdx = null;
  for (let d = 0; d < days.length; d++) {
    let dayPnL = 0;
    for (const pts of days[d]) {
      const pnl = pts * size * PV;
      realized += pnl; dayPnL += pnl;
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
  const dayKeys = [...new Set(bars.map((b) => etYmd(b.t)))].sort((a, b) => a - b);
  const S = Lab.buildAll(bars);            // build ALL signals once, full warmup
  const sig = S[KEY];

  console.log(`POWER-HOUR (#42) — FULL ~90-DAY CHART (TradingView MNQ 5m).`);
  console.log(`Span: ${dayKeys[0]} -> ${dayKeys[dayKeys.length - 1]}  |  ${dayKeys.length} ET trading days  |  ${bars.length} bars.`);
  console.log(`Yahoo's 60d cap could only see the last 58 of these; this run adds Mar 8 -> early Apr. Net @5 MNQ ($10/pt) and @1 MNQ ($2/pt).\n`);

  // ---------- (1) OVERALL ----------
  const r = Lab.runSignals(bars, sig);
  const net5 = r.netPts * PV5, net1 = r.netPts * PV1, dd5 = r.ddPts * PV5, dd1 = r.ddPts * PV1;
  const wd5 = Math.abs(r.worstDayPts * PV5), wd1 = Math.abs(r.worstDayPts * PV1);
  console.log(`(1) OVERALL EDGE (all ${dayKeys.length} days)`);
  console.log(`  Trades ${r.n}   Win% ${f(r.winRate, 1)}   PF ${f(r.pf, 2)}   MaxLossStreak ${r.maxLossStreak}`);
  console.log(`  Net:       ${money(net5)} @5 MNQ    ${money(net1)} @1 MNQ`);
  console.log(`  MaxDD:     ${money(-dd5)} @5 MNQ    ${money(-dd1)} @1 MNQ   (vs $${MLL} trailing MLL)`);
  console.log(`  WorstDay:  ${money(-wd5)} @5 MNQ    ${money(-wd1)} @1 MNQ   (vs $${DLL} DLL)`);
  console.log(`  Naive Combine flags @5: ${wd5 >= DLL ? "DLL!" : "ok"} / ${dd5 >= MLL ? "MLL!" : "ok"}    @1: ${wd1 >= DLL ? "DLL!" : "ok"} / ${dd1 >= MLL ? "MLL!" : "ok"}`);
  console.log(`  58d Yahoo baseline for reference: PF 1.82, +$11,461 @5MNQ / +$2,292 @1MNQ, 85 trades, worstDay -$773, maxDD $1,808.\n`);

  // ---------- (2) ROLLING 30-TRADING-DAY WINDOWS ----------
  const WIN = 30, STEP = Math.max(1, Math.floor((dayKeys.length - WIN) / 4));   // 5 windows spanning the range
  const windows = [];
  for (let start = 0; start + WIN <= dayKeys.length && windows.length < 5; start += STEP) {
    windows.push({ lo: dayKeys[start], hi: dayKeys[start + WIN - 1] });
  }
  if (windows[windows.length - 1].hi !== dayKeys[dayKeys.length - 1]) windows.push({ lo: dayKeys[dayKeys.length - WIN], hi: dayKeys[dayKeys.length - 1] });

  console.log(`(2) ROLLING ${WIN}-TRADING-DAY WINDOWS (does the edge persist across the whole quarter, or live in one stretch?)`);
  const hdr = "Window".padEnd(22) + "Trd".padStart(4) + "Win%".padStart(6) + "PF".padStart(6) +
    "Net@5".padStart(10) + "Net@1".padStart(9) + "MaxDD@5".padStart(9) + "WrstDay@5".padStart(11) + "$3k?".padStart(6) + "5MNQ".padStart(6);
  console.log("  " + hdr); console.log("  " + "-".repeat(hdr.length));
  const winResults = [];
  for (const w of windows) {
    const wr = Lab.runSignals(bars, maskToWindow(bars, sig, w.lo, w.hi));
    winResults.push(wr);
    const n5 = wr.netPts * PV5, n1 = wr.netPts * PV1, d5 = wr.ddPts * PV5, w5 = Math.abs(wr.worstDayPts * PV5);
    const surv = (w5 < DLL && d5 < MLL) ? "OK" : (w5 >= DLL ? "DLL!" : "MLL!");
    const label = `${String(w.lo).slice(4, 6)}/${String(w.lo).slice(6)}->${String(w.hi).slice(4, 6)}/${String(w.hi).slice(6)}`;
    console.log("  " + label.padEnd(22) + String(wr.n).padStart(4) + (f(wr.winRate, 0) + "%").padStart(6) +
      (wr.pf === Infinity ? "inf" : f(wr.pf, 2)).padStart(6) + money(n5).padStart(10) + money(n1).padStart(9) +
      ("$" + f(d5)).padStart(9) + ("-$" + f(w5)).padStart(11) + (n5 >= 3000 ? "yes" : "no").padStart(6) + surv.padStart(6));
  }
  const allPos = winResults.every((wr) => wr.netPts > 0);
  const breaches = winResults.filter((wr) => Math.abs(wr.worstDayPts * PV5) >= DLL || wr.ddPts * PV5 >= MLL).length;
  console.log(`  Verdict: positive in ${winResults.filter((wr) => wr.netPts > 0).length}/${winResults.length} windows${allPos ? " (all)" : ""};  Combine breaches @5 MNQ: ${breaches}/${winResults.length};  PF range ${f(Math.min(...winResults.map((x) => x.pf).filter(isFinite)), 2)}->${f(Math.max(...winResults.map((x) => x.pf).filter(isFinite)), 2)}.\n`);

  // ---------- (3) CHRONOLOGICAL COMBINE + RETURN-ORDER STRESS ----------
  const ledger = Lab.runLedger(bars, sig);
  const dayMap = new Map();
  for (const t of ledger) { if (!dayMap.has(t.date)) dayMap.set(t.date, []); dayMap.get(t.date).push(t.pts); }
  const days = [...dayMap.values()];
  console.log(`(3) $50K COMBINE — ${ledger.length} trades across ${days.length} trading days. MLL $${MLL} (trails peak, locks at +$${MLL}), DLL $${DLL}/day, pass +$${TARGET}.`);
  console.log(`  REAL CHRONOLOGICAL ORDER:`);
  for (const size of [1, 3, 5]) {
    const sr = simulate(days, size);
    console.log(`    flat ${size} MNQ -> ${sr.outcome.padEnd(11)} final ${money(sr.profit).padStart(10)}  peak ${money(sr.peak).padStart(10)}  ${sr.passDayIdx == null ? "" : "passed on active day #" + (sr.passDayIdx + 1)}`);
  }
  const N = 10000, rng = mulberry32(12345);
  console.log(`\n  RETURN-ORDER STRESS — ${N} random permutations of the ${days.length} trading days:`);
  console.log("    " + "Size".padEnd(10) + "Pass%".padStart(8) + "Fail-MLL%".padStart(11) + "Fail-DLL%".padStart(11) + "NoPass%".padStart(9) + "MedPassDay".padStart(12));
  for (const size of [1, 3, 5]) {
    let pass = 0, mll = 0, dll = 0, inc = 0; const pd = [];
    for (let n = 0; n < N; n++) {
      const sr = simulate(shuffled(days, rng), size);
      if (sr.outcome === "PASS") { pass++; pd.push(sr.passDayIdx + 1); }
      else if (sr.outcome === "MLL") mll++; else if (sr.outcome === "DLL") dll++; else inc++;
    }
    pd.sort((a, b) => a - b);
    const med = pd.length ? pd[Math.floor(pd.length / 2)] : null;
    console.log("    " + ("flat " + size + " MNQ").padEnd(10) + (f(pass / N * 100, 1) + "%").padStart(8) + (f(mll / N * 100, 1) + "%").padStart(11) +
      (f(dll / N * 100, 1) + "%").padStart(11) + (f(inc / N * 100, 1) + "%").padStart(9) + (med == null ? "—" : "#" + med).padStart(12));
  }

  console.log(`\nNOTE: This 89-day sample now SPANS more regime than the 58-day Yahoo window — it includes March, which Yahoo's 60d cap hid.`);
  console.log(`If flat 3 still dominates here, the earlier "size flat 3, skip staging" call holds across a wider sample, not just spring.`);
})();
