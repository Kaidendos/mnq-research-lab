// =============================================================
//  optimize10.js — tune the exit bracket of the catalog13 TOP 10
//  (the 10 best-by-13d-net methods EXCLUDING the locked champion).
//
//  The ENTRY method of each is fixed (that IS the strategy). What we optimize
//  is the common exit: stop multiple x ATR and target multiple x ATR. We sweep
//  a grid on the 13-DAY chart, pick the best Combine-FEASIBLE config (worst day
//  < $1000 AND maxDD < $2000 @5 MNQ; tiebreak = net, then PF), and ALSO report
//  that same config on the 58-day chart as an out-of-sample / overfit check.
//
//  Reuses catalog13.js's entry definitions (ctxOf + NEW) and lab-new4's
//  buildAll/runLedger/tally — zero strategy reimplementation.
//
//  WARNING: tuning a grid on 13 days IS curve-fitting. The 58-day column is the
//  reality check; expect most "optimized" 13d gains to shrink or vanish there.
//
//  DATA-ONLY / TopStep-compliant: reads local data, never places an order.
//  Champion stays locked and is NOT included here.
//  Run:  node optimize10.js
// =============================================================
"use strict";

const fs = require("fs");
const path = require("path");
require("./public/indicators.js");
const Lab = require("./lab-new4");
const Cat = require("./catalog13");

const DPP = 10;                              // $/pt @ 5 MNQ (live size)
const DLL = Lab.DLL, MLL = Lab.MLL;
const STOPS = [0.8, 1.0, 1.2, 1.5, 2.0];     // stop x ATR
const TGTS = [1.2, 1.5, 1.8, 2.4, 3.0];      // target x ATR
const BASE_S = Cat.STOP_MULT, BASE_T = Cat.TGT_MULT;   // catalog13 common exit (1.2/1.8)
const OUT_JSON = path.join(__dirname, "logs", "optimize10-results.json");
const OUT_MD = path.join(__dirname, "logs", "optimize10-report.md");

// Top 10 by 13d net, champion (#7) excluded. lab = dir from buildAll; new = fn(C,i).
const METHODS = [
  { kind: "lab", key: "rsiBandRide", label: "49. RSI band-ride dip buy" },
  { kind: "new", key: "n44_threeInside", label: "Three-inside up/down" },
  { kind: "new", key: "n29_mom5bar", label: "5-bar momentum vs ATR+EMA50" },
  { kind: "new", key: "n50_starPattern", label: "Morning/evening star" },
  { kind: "lab", key: "nr4Break", label: "25. NR4 narrow-range break" },
  { kind: "lab", key: "pinBar", label: "32. Pin-bar rejection" },
  { kind: "lab", key: "fakeout", label: "39. Failed-breakout fade" },
  { kind: "new", key: "n69_rocAccel", label: "ROC acceleration" },
  { kind: "lab", key: "don55", label: "23. Donchian-55 break" },
  { kind: "new", key: "n04_ibsExt", label: "Internal Bar Strength extreme" },
];

const NEWMAP = new Map(Cat.NEW.map((m) => [m[0], m[3]]));

function dirAtFor(method, ctx, S) {
  if (method.kind === "lab") { const arr = S[method.key]; return (i) => (arr[i] ? arr[i].dir : 0); }
  const fn = NEWMAP.get(method.key); return (i) => fn(ctx, i);
}

function evalCfg(bars, ctx, dirAt, sMul, tMul) {
  const sig = new Array(bars.length).fill(null);
  for (let i = 210; i < bars.length; i++) {
    const a = ctx.atr[i]; if (a == null || !(a > 0)) continue;
    let d = 0; try { d = dirAt(i) || 0; } catch (e) { continue; }
    if (d === 1) sig[i] = { dir: 1, entry: ctx.c[i], stop: ctx.c[i] - sMul * a, target: ctx.c[i] + tMul * a };
    else if (d === -1) sig[i] = { dir: -1, entry: ctx.c[i], stop: ctx.c[i] + sMul * a, target: ctx.c[i] - tMul * a };
  }
  const t = Lab.tally(Lab.runLedger(bars, sig));
  const net$ = t.netPts * DPP, dd$ = t.ddPts * DPP, wd$ = Math.abs(t.worstDayPts) * DPP;
  return { s: sMul, t: tMul, rr: +(tMul / sMul).toFixed(2), n: t.n, win: +t.winRate.toFixed(1), pf: t.pf === Infinity ? 99 : +t.pf.toFixed(2), net$: Math.round(net$), dd$: Math.round(dd$), wd$: Math.round(wd$), feasible: wd$ < DLL && dd$ < MLL };
}

function loadJson(p) { return JSON.parse(fs.readFileSync(p, "utf8")).filter((b) => b && isFinite(b.c)).sort((a, b) => a.t - b.t); }
function spanOf(bars) { return [bars[0].t, bars[bars.length - 1].t].map((s) => new Date(s * 1000).toISOString().slice(0, 10)); }
const dol = (n) => (n >= 0 ? "+$" : "-$") + Math.abs(n);

function main() {
  const t0 = Date.now();
  const bars13 = Lab.loadCsv(Lab.CSV_13), bars58 = loadJson(path.join(__dirname, "data", "nq-5m.json"));
  const span13 = spanOf(bars13), span58 = spanOf(bars58);
  const ctx13 = Cat.ctxOf(bars13), S13 = Lab.buildAll(bars13);
  const ctx58 = Cat.ctxOf(bars58), S58 = Lab.buildAll(bars58);

  console.log(`OPTIMIZE-10 — tune exit bracket (stop x ATR / target x ATR) of the catalog13 TOP 10 (champion excluded).`);
  console.log(`13d: ${span13[0]} -> ${span13[1]} (${bars13.length} bars)  |  58d: ${span58[0]} -> ${span58[1]} (${bars58.length} bars)`);
  console.log(`Sweep: stops {${STOPS.join(", ")}} x targets {${TGTS.join(", ")}} = ${STOPS.length * TGTS.length} configs/method, optimized on 13d, feasibility-first. $ @5 MNQ.\n`);

  const rows = [];
  for (const m of METHODS) {
    const dir13 = dirAtFor(m, ctx13, S13), dir58 = dirAtFor(m, ctx58, S58);
    const base = evalCfg(bars13, ctx13, dir13, BASE_S, BASE_T);
    const grid = [];
    for (const s of STOPS) for (const tt of TGTS) grid.push(evalCfg(bars13, ctx13, dir13, s, tt));
    // feasibility-first, then net, then PF
    grid.sort((a, b) => (b.feasible - a.feasible) || (b.net$ - a.net$) || (b.pf - a.pf));
    const best = grid[0];
    const oos = evalCfg(bars58, ctx58, dir58, best.s, best.t);     // SAME tuned config, 58d
    const base58 = evalCfg(bars58, ctx58, dir58, BASE_S, BASE_T);
    rows.push({ label: m.label, key: m.key, base, best, oos, base58, delta: best.net$ - base.net$, oosDelta: oos.net$ - base58.net$ });
  }
  rows.sort((a, b) => b.best.net$ - a.best.net$);

  const H = "Method".padEnd(31) + "Base13d".padStart(9) + "OptCfg".padStart(9) + "Opt13d".padStart(9) + "Trd".padStart(5) + "Win%".padStart(6) + "PF".padStart(6) + "feas".padStart(5) + "  58d(same cfg)".padStart(15);
  console.log(H); console.log("-".repeat(H.length));
  for (const r of rows) {
    console.log(r.label.slice(0, 30).padEnd(31) + dol(r.base.net$).padStart(9) + `${r.best.s}/${r.best.t}`.padStart(9) + dol(r.best.net$).padStart(9) + String(r.best.n).padStart(5) + (r.best.win + "%").padStart(6) + String(r.best.pf).padStart(6) + (r.best.feasible ? "ok" : "DD!").padStart(5) + ("  " + dol(r.oos.net$) + ` (${r.oos.n}t)`).padStart(15));
  }

  const feas = rows.filter((r) => r.best.feasible);
  const heldUp = rows.filter((r) => r.best.feasible && r.oos.net$ > 0);
  console.log(`\nFeasible after tuning (13d): ${feas.length}/10.`);
  console.log(`Still net-positive on 58d at the SAME tuned config (overfit survivors): ${heldUp.length}/10.`);
  for (const r of heldUp) console.log(`   ${r.label}: 13d ${dol(r.best.net$)} @${r.best.s}/${r.best.t} (${r.best.n}t ${r.best.win}%) | 58d ${dol(r.oos.net$)} (${r.oos.n}t ${r.oos.win}%)`);

  // ---- save ----
  fs.writeFileSync(OUT_JSON, JSON.stringify({ generatedAt: new Date().toISOString(), span13, span58, stops: STOPS, targets: TGTS, baseExit: [BASE_S, BASE_T], rows }, null, 2));
  const md = [];
  md.push(`# Optimize-10 — exit-bracket tuning of the catalog13 top 10 (${new Date().toISOString().slice(0, 10)})`);
  md.push(`\nThe 10 best-by-13d-net methods **excluding the locked champion**. Entry fixed; only the exit (stop×ATR / target×ATR) tuned. Swept ${STOPS.length}×${TGTS.length}=${STOPS.length * TGTS.length} configs on the **13-day** chart, feasibility-first (worst day < $${DLL} AND maxDD < $${MLL} @5 MNQ). The 58-day column applies the SAME tuned config — the overfit reality check. Dollars @5 MNQ.`);
  md.push(`\n> WARNING: tuning a grid on 13 days is textbook curve-fitting. A config only means something if it ALSO survives the 58-day column. Champion NOT included — it stays locked. Gross only.`);
  md.push(`\n## Results (ranked by optimized 13d net)\n`);
  md.push(`| Method | Base 13d (1.2/1.8) | Opt cfg (S/T) | Opt 13d | Trd/Win | PF | Feasible | 58d @same cfg | Base 58d (1.2/1.8) |`);
  md.push(`|--------|------:|:--:|------:|:--:|---:|:--:|------:|------:|`);
  for (const r of rows) md.push(`| ${r.label} | ${dol(r.base.net$)} | ${r.best.s}/${r.best.t} | ${dol(r.best.net$)} | ${r.best.n}/${r.best.win}% | ${r.best.pf} | ${r.best.feasible ? "yes" : "DD!"} | ${dol(r.oos.net$)} (${r.oos.n}t) | ${dol(r.base58.net$)} |`);
  md.push(`\n## Overfit survivors (feasible on 13d AND still net-positive on 58d at the tuned config): ${heldUp.length}/10\n`);
  if (heldUp.length) for (const r of heldUp) md.push(`- **${r.label}** — 13d ${dol(r.best.net$)} @ ${r.best.s}/${r.best.t} (${r.best.n}t, ${r.best.win}%); 58d ${dol(r.oos.net$)} (${r.oos.n}t, ${r.oos.win}%)`);
  else md.push(`_None — every tuned config that looked good on 13d failed to hold on 58d. That's the curve-fitting lesson in one line._`);
  md.push(`\nReminder: the locked **champion** beats all of these on the metric that matters — it is feasible AND net-positive on 13d, 58d, AND 90d (+$16,703, 96% Combine pass). DATA-ONLY: nothing live touched.`);
  fs.writeFileSync(OUT_MD, md.join("\n") + "\n");

  console.log(`\nSaved ${OUT_JSON} and ${OUT_MD}. (${((Date.now() - t0) / 1000).toFixed(1)}s)`);
  console.log("DATA-ONLY: champion locked & untouched.");
}

main();
