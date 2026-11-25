// =============================================================
//  merge10.js — the "have fun, try to MAKE them work" sandbox.
//
//  The catalog13 top-10 challengers all FAIL the Combine walls: they fire too
//  often and too wide, so worst-day / drawdown blow past $1k/$2k. optimize10.js
//  proved tuning the exit bracket alone can't fix that (0/10 feasible).
//
//  So here we borrow the CHAMPION's discipline and try to rescue them three ways:
//    (A) FOCUS    — restrict the entry to the power hour (+ ADX>20), 1 trade/day.
//    (B) MERGE    — confluence: require TWO methods to agree on direction
//                   (B fires now AND A agreed within the last 3 bars).
//    (C) BRAKES   — daily circuit breaker: stop trading the day after -$X realized,
//                   plus a max-trades-per-day cap (mechanically bounds the DLL).
//
//  A variant "wins" only if it is Combine-FEASIBLE *and* net-positive on BOTH
//  the 13-day and 58-day charts. Everything reuses catalog13/lab-new4 — zero
//  strategy reimplementation. DATA-ONLY: never places an order. Champion locked.
//  Run:  node merge10.js
// =============================================================
"use strict";

const fs = require("fs");
const path = require("path");
require("./public/indicators.js");
const Lab = require("./lab-new4");
const Cat = require("./catalog13");

const DPP = 10;                       // $/pt @ 5 MNQ (live size)
const DLL = Lab.DLL, MLL = Lab.MLL;
const PH_START = 900, PH_END = 945;   // champion's power-hour window
const OUT_JSON = path.join(__dirname, "logs", "merge10-results.json");
const OUT_MD = path.join(__dirname, "logs", "merge10-report.md");

const METHODS = [
  { kind: "lab", key: "rsiBandRide", label: "RSI band-ride" },
  { kind: "new", key: "n44_threeInside", label: "Three-inside" },
  { kind: "new", key: "n29_mom5bar", label: "5-bar momentum" },
  { kind: "new", key: "n50_starPattern", label: "Morning/evening star" },
  { kind: "lab", key: "nr4Break", label: "NR4 break" },
  { kind: "lab", key: "pinBar", label: "Pin-bar" },
  { kind: "lab", key: "fakeout", label: "Failed-breakout fade" },
  { kind: "new", key: "n69_rocAccel", label: "ROC acceleration" },
  { kind: "lab", key: "don55", label: "Donchian-55 break" },
  { kind: "new", key: "n04_ibsExt", label: "IBS extreme" },
];
const NEWMAP = new Map(Cat.NEW.map((m) => [m[0], m[3]]));

// per-sample: direction array for each method key
function dirArrays(bars, ctx, S) {
  const out = {};
  for (const m of METHODS) {
    const a = new Array(bars.length).fill(0);
    if (m.kind === "lab") { const arr = S[m.key]; for (let i = 210; i < bars.length; i++) a[i] = arr[i] ? arr[i].dir : 0; }
    else { const fn = NEWMAP.get(m.key); for (let i = 210; i < bars.length; i++) { try { a[i] = fn(ctx, i) || 0; } catch (e) { a[i] = 0; } } }
    out[m.key] = a;
  }
  return out;
}

// transforms on a dir array -----------------------------------
function restrictPH(dir, ctx, useAdx) {
  return dir.map((d, i) => (d !== 0 && ctx.mins[i] >= PH_START && ctx.mins[i] <= PH_END && (!useAdx || (ctx.adx && ctx.adx[i] != null && ctx.adx[i] > 20))) ? d : 0);
}
function confluence(dirA, dirB, W) {            // B now AND A agreed within last W bars
  const out = new Array(dirB.length).fill(0);
  for (let i = 0; i < dirB.length; i++) {
    if (dirB[i] === 0) continue;
    for (let j = Math.max(0, i - W); j <= i; j++) { if (dirA[j] === dirB[i]) { out[i] = dirB[i]; break; } }
  }
  return out;
}

function buildSig(bars, ctx, dir, s, t) {
  const sig = new Array(bars.length).fill(null);
  for (let i = 210; i < bars.length; i++) {
    const a = ctx.atr[i]; if (a == null || !(a > 0) || dir[i] === 0) continue;
    sig[i] = dir[i] === 1 ? { dir: 1, entry: ctx.c[i], stop: ctx.c[i] - s * a, target: ctx.c[i] + t * a } : { dir: -1, entry: ctx.c[i], stop: ctx.c[i] + s * a, target: ctx.c[i] - t * a };
  }
  return sig;
}
// daily brakes applied to a realized ledger (one position at a time → sequential)
function applyDaily(ledger, maxTrades, dailyStopUSD) {
  if (!maxTrades && !dailyStopUSD) return ledger;
  const out = [], st = new Map();
  for (const tr of ledger.slice().sort((a, b) => a.entryT - b.entryT)) {
    const s = st.get(tr.date) || { n: 0, cum: 0, stopped: false };
    if (s.stopped || (maxTrades && s.n >= maxTrades)) { st.set(tr.date, s); continue; }
    out.push(tr); s.n++; s.cum += tr.pts * DPP;
    if (dailyStopUSD && s.cum <= -dailyStopUSD) s.stopped = true;
    st.set(tr.date, s);
  }
  return out;
}
function evalLedger(ledger) {
  const t = Lab.tally(ledger);
  const net$ = t.netPts * DPP, dd$ = t.ddPts * DPP, wd$ = Math.abs(t.worstDayPts) * DPP;
  return { n: t.n, win: +t.winRate.toFixed(1), pf: t.pf === Infinity ? 99 : +t.pf.toFixed(2), net$: Math.round(net$), dd$: Math.round(dd$), wd$: Math.round(wd$), feasible: wd$ < DLL && dd$ < MLL };
}

function loadJson(p) { return JSON.parse(fs.readFileSync(p, "utf8")).filter((b) => b && isFinite(b.c)).sort((a, b) => a.t - b.t); }
function spanOf(bars) { return [bars[0].t, bars[bars.length - 1].t].map((s) => new Date(s * 1000).toISOString().slice(0, 10)); }
const dol = (n) => (n >= 0 ? "+$" : "-$") + Math.abs(n);

// confluence pairs to try (conceptually complementary)
const PAIRS = [
  ["rsiBandRide", "n29_mom5bar", "RSI-dip + 5-bar mom"],
  ["n44_threeInside", "pinBar", "Three-inside + Pin-bar"],
  ["nr4Break", "don55", "NR4 + Donchian-55 break"],
  ["n69_rocAccel", "n29_mom5bar", "ROC + 5-bar mom"],
  ["n04_ibsExt", "n44_threeInside", "IBS + Three-inside"],
  ["n50_starPattern", "rsiBandRide", "Star + RSI-dip"],
];

function main() {
  const t0 = Date.now();
  const bars13 = Lab.loadCsv(Lab.CSV_13), bars58 = loadJson(path.join(__dirname, "data", "nq-5m.json"));
  const span13 = spanOf(bars13), span58 = spanOf(bars58);
  const ctx13 = Cat.ctxOf(bars13), S13 = Lab.buildAll(bars13), D13 = dirArrays(bars13, ctx13, S13);
  const ctx58 = Cat.ctxOf(bars58), S58 = Lab.buildAll(bars58), D58 = dirArrays(bars58, ctx58, S58);

  console.log(`MERGE-10 — trying to RESCUE the top-10 challengers (focus / merge / brakes). Champion excluded & locked.`);
  console.log(`13d ${span13[0]}->${span13[1]} | 58d ${span58[0]}->${span58[1]} | win = feasible AND net+ on BOTH. $ @5 MNQ.\n`);

  // each variant: {name, fam, dir13, dir58, s, t, maxTrades, dailyStop}
  const variants = [];

  // (A) FOCUS — power hour + ADX>20, 1 trade/day, 1.2/1.8
  for (const m of METHODS) variants.push({ name: `[A] ${m.label} · PH+ADX, 1/day`, fam: "FOCUS", d13: restrictPH(D13[m.key], ctx13, true), d58: restrictPH(D58[m.key], ctx58, true), s: 1.2, t: 1.8, maxTrades: 1, dailyStop: 0 });

  // (B) MERGE — confluence pairs (W=3), 1.2/1.8, RTH ; and a braked version
  for (const [a, b, nm] of PAIRS) {
    variants.push({ name: `[B] ${nm} (confluence)`, fam: "MERGE", d13: confluence(D13[a], D13[b], 3), d58: confluence(D58[a], D58[b], 3), s: 1.2, t: 1.8, maxTrades: 0, dailyStop: 0 });
    variants.push({ name: `[B] ${nm} (confluence + brakes)`, fam: "MERGE", d13: confluence(D13[a], D13[b], 3), d58: confluence(D58[a], D58[b], 3), s: 1.2, t: 1.8, maxTrades: 2, dailyStop: 800 });
  }

  // (C) BRAKES — full RTH entry, tighter risk + daily circuit breaker + cap
  for (const m of METHODS) variants.push({ name: `[C] ${m.label} · brake $700, 2/day`, fam: "BRAKES", d13: D13[m.key], d58: D58[m.key], s: 1.0, t: 2.0, maxTrades: 2, dailyStop: 700 });

  const rows = [];
  for (const v of variants) {
    const l13 = applyDaily(Lab.runLedger(bars13, buildSig(bars13, ctx13, v.d13, v.s, v.t)), v.maxTrades, v.dailyStop);
    const l58 = applyDaily(Lab.runLedger(bars58, buildSig(bars58, ctx58, v.d58, v.s, v.t)), v.maxTrades, v.dailyStop);
    rows.push({ name: v.name, fam: v.fam, r13: evalLedger(l13), r58: evalLedger(l58) });
  }

  const winners = rows.filter((r) => r.r13.feasible && r.r13.net$ > 0 && r.r58.feasible && r.r58.net$ > 0);
  const feas13 = rows.filter((r) => r.r13.feasible);

  const H = "Variant".padEnd(40) + "13dNet".padStart(9) + "13dFeas".padStart(8) + "Trd".padStart(5) + "  58dNet".padStart(9) + "58dFeas".padStart(8) + "Trd".padStart(5) + "  WIN".padStart(5);
  console.log(H); console.log("-".repeat(H.length));
  for (const r of rows) {
    const win = (r.r13.feasible && r.r13.net$ > 0 && r.r58.feasible && r.r58.net$ > 0) ? "★" : "";
    console.log(r.name.slice(0, 39).padEnd(40) + dol(r.r13.net$).padStart(9) + (r.r13.feasible ? "ok" : "DD!").padStart(8) + String(r.r13.n).padStart(5) + ("  " + dol(r.r58.net$)).padStart(9) + (r.r58.feasible ? "ok" : "DD!").padStart(8) + String(r.r58.n).padStart(5) + win.padStart(5));
  }

  console.log(`\nFeasible on 13d: ${feas13.length}/${rows.length}.  WINNERS (feasible AND net+ on BOTH samples): ${winners.length}.`);
  for (const w of winners) console.log(`  ★ ${w.name} [${w.fam}] — 13d ${dol(w.r13.net$)} (${w.r13.n}t ${w.r13.win}% PF${w.r13.pf}) | 58d ${dol(w.r58.net$)} (${w.r58.n}t ${w.r58.win}% PF${w.r58.pf})`);

  // ---- save ----
  fs.writeFileSync(OUT_JSON, JSON.stringify({ generatedAt: new Date().toISOString(), span13, span58, winners: winners.map((w) => w.name), rows }, null, 2));
  const md = [];
  md.push(`# Merge-10 — trying to rescue the top-10 challengers (${new Date().toISOString().slice(0, 10)})`);
  md.push(`\nThe catalog13 top-10 (champion excluded) all failed the Combine walls; optimize10 showed exit-tuning alone can't fix it. Here we borrow the champion's discipline three ways — **[A] FOCUS** (power-hour + ADX>20, 1 trade/day), **[B] MERGE** (require two methods to agree, ±3-bar window), **[C] BRAKES** (daily circuit breaker + trade cap). A variant **wins** only if it is Combine-feasible AND net-positive on BOTH the 13-day and 58-day charts. Dollars @5 MNQ. Gross only.`);
  md.push(`\n- Variants tested: **${rows.length}**  |  Feasible on 13d: **${feas13.length}**  |  Winners (both samples): **${winners.length}**`);
  md.push(`\n## All variants\n`);
  md.push(`| Variant | Fam | 13d Net | 13d Feas | 13d Trd | 58d Net | 58d Feas | 58d Trd | Win |`);
  md.push(`|---------|-----|------:|:--:|--:|------:|:--:|--:|:--:|`);
  for (const r of rows) md.push(`| ${r.name} | ${r.fam} | ${dol(r.r13.net$)} | ${r.r13.feasible ? "yes" : "DD!"} | ${r.r13.n} | ${dol(r.r58.net$)} | ${r.r58.feasible ? "yes" : "DD!"} | ${r.r58.n} | ${(r.r13.feasible && r.r13.net$ > 0 && r.r58.feasible && r.r58.net$ > 0) ? "★" : ""} |`);
  md.push(`\n## Winners (feasible + net-positive on BOTH samples): ${winners.length}\n`);
  if (winners.length) for (const w of winners) md.push(`- **★ ${w.name}** [${w.fam}] — 13d ${dol(w.r13.net$)} (${w.r13.n}t, ${w.r13.win}%, PF ${w.r13.pf}); 58d ${dol(w.r58.net$)} (${w.r58.n}t, ${w.r58.win}%, PF ${w.r58.pf})`);
  else md.push(`_None survived both samples. Discipline + merging shrinks the drawdown but doesn't manufacture an edge where there isn't one._`);
  md.push(`\nReminder: even any winner here is a CANDIDATE, not a replacement — the locked champion already clears 13d/58d/90d (+$16,703, 96% Combine pass) with no rescue needed. DATA-ONLY: nothing live touched.`);
  fs.writeFileSync(OUT_MD, md.join("\n") + "\n");

  console.log(`\nSaved ${OUT_JSON} and ${OUT_MD}. (${((Date.now() - t0) / 1000).toFixed(1)}s)  DATA-ONLY: champion locked.`);
}

main();
