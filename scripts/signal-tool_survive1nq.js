// =============================================================
//  survive1nq.js — hunt for a strategy that SURVIVES and profits at 1 NQ.
//
//  1 NQ = $20/pt = 2x the live 5-MNQ size, so the Combine walls bite twice as
//  hard. Feasible @1 NQ means worst day < 50 pts ($1000 DLL) AND max drawdown
//  < 100 pts ($2000 MLL). The champion FAILS this (it had a -$1,545 day at 1NQ).
//
//  Strategy to get there = very tight per-day risk. For each candidate entry
//  (the catalog13 top-10 + champion + the Three-inside+Pin-bar merge) we sweep:
//      focus  : power-hour+ADX>20   vs   full RTH
//      stop   : 0.6 / 0.8 / 1.0 x ATR     (tight — caps per-trade $)
//      target : 1.5 / 2.0 / 2.5 x ATR
//      cap    : 1 or 2 trades/day
//      brake  : daily circuit breaker off / $600 (in 1-NQ dollars)
//  Pick each candidate's best config that is feasible AND net+ on BOTH the
//  13-day and 58-day charts (@1 NQ). Reuses catalog13/lab-new4 — zero rewrite.
//
//  DATA-ONLY / TopStep-compliant: never places an order. Champion stays locked.
//  Run:  node survive1nq.js
// =============================================================
"use strict";

const fs = require("fs");
const path = require("path");
require("./public/indicators.js");
const Lab = require("./lab-new4");
const Cat = require("./catalog13");

const PV = 20;                        // $/pt @ 1 NQ  (this is the whole point)
const DLL = Lab.DLL, MLL = Lab.MLL;   // 1000 / 2000
const PH_START = 900, PH_END = 945;
const OUT_JSON = path.join(__dirname, "logs", "survive1nq-results.json");
const OUT_MD = path.join(__dirname, "logs", "survive1nq-report.md");

const STOPS = [0.6, 0.8, 1.0], TGTS = [1.5, 2.0, 2.5];
const CAPS = [1, 2], BRAKES = [0, 600];

const NEWMAP = new Map(Cat.NEW.map((m) => [m[0], m[3]]));
const CANDIDATES = [
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
  { kind: "champ", key: "CHAMPION", label: "Champion (PH+EMA200+ADX)" },
  { kind: "merge", key: "threeInside+pinBar", label: "Three-inside + Pin-bar (merge)" },
];

function dirArrayFor(cand, bars, ctx, S) {
  const a = new Array(bars.length).fill(0);
  if (cand.kind === "lab") { const arr = S[cand.key]; for (let i = 210; i < bars.length; i++) a[i] = arr[i] ? arr[i].dir : 0; }
  else if (cand.kind === "new") { const fn = NEWMAP.get(cand.key); for (let i = 210; i < bars.length; i++) { try { a[i] = fn(ctx, i) || 0; } catch (e) { a[i] = 0; } } }
  else if (cand.kind === "champ") { for (let i = 210; i < bars.length; i++) { try { a[i] = Cat.championDir(ctx, i) || 0; } catch (e) { a[i] = 0; } } }
  else if (cand.kind === "merge") { // Three-inside now AND Pin-bar agreed within last 3 bars
    const ti = new Array(bars.length).fill(0); const fn = NEWMAP.get("n44_threeInside");
    for (let i = 210; i < bars.length; i++) { try { ti[i] = fn(ctx, i) || 0; } catch (e) { ti[i] = 0; } }
    const pb = S["pinBar"];
    for (let i = 210; i < bars.length; i++) { if (ti[i] === 0) continue; for (let j = Math.max(0, i - 3); j <= i; j++) { const d = pb[j] ? pb[j].dir : 0; if (d === ti[i]) { a[i] = ti[i]; break; } } }
  }
  return a;
}
function restrictPHADX(dir, ctx) {
  return dir.map((d, i) => (d !== 0 && ctx.mins[i] >= PH_START && ctx.mins[i] <= PH_END && ctx.adx && ctx.adx[i] != null && ctx.adx[i] > 20) ? d : 0);
}
function buildSig(bars, ctx, dir, s, t) {
  const sig = new Array(bars.length).fill(null);
  for (let i = 210; i < bars.length; i++) {
    const a = ctx.atr[i]; if (a == null || !(a > 0) || dir[i] === 0) continue;
    sig[i] = dir[i] === 1 ? { dir: 1, entry: ctx.c[i], stop: ctx.c[i] - s * a, target: ctx.c[i] + t * a } : { dir: -1, entry: ctx.c[i], stop: ctx.c[i] + s * a, target: ctx.c[i] - t * a };
  }
  return sig;
}
function applyDaily(ledger, maxTrades, dailyStopUSD) {
  if (!maxTrades && !dailyStopUSD) return ledger;
  const out = [], st = new Map();
  for (const tr of ledger.slice().sort((a, b) => a.entryT - b.entryT)) {
    const s = st.get(tr.date) || { n: 0, cum: 0, stopped: false };
    if (s.stopped || (maxTrades && s.n >= maxTrades)) { st.set(tr.date, s); continue; }
    out.push(tr); s.n++; s.cum += tr.pts * PV;
    if (dailyStopUSD && s.cum <= -dailyStopUSD) s.stopped = true;
    st.set(tr.date, s);
  }
  return out;
}
function evalLedger(ledger) {
  const t = Lab.tally(ledger);
  const net$ = t.netPts * PV, dd$ = t.ddPts * PV, wd$ = Math.abs(t.worstDayPts) * PV;
  return { n: t.n, win: +t.winRate.toFixed(1), pf: t.pf === Infinity ? 99 : +t.pf.toFixed(2), mls: t.maxLossStreak, net$: Math.round(net$), dd$: Math.round(dd$), wd$: Math.round(wd$), feasible: wd$ < DLL && dd$ < MLL };
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

  console.log(`SURVIVE-1NQ — hunting a strategy feasible + profitable at 1 NQ ($20/pt). Feasible = worstDay<$${DLL} AND maxDD<$${MLL}.`);
  console.log(`13d ${span13[0]}->${span13[1]} | 58d ${span58[0]}->${span58[1]} | grid: focus{PH+ADX,RTH} x stop${JSON.stringify(STOPS)} x tgt${JSON.stringify(TGTS)} x cap${JSON.stringify(CAPS)} x brake${JSON.stringify(BRAKES)}\n`);

  const best = [];
  for (const cand of CANDIDATES) {
    const dRaw13 = dirArrayFor(cand, bars13, ctx13, S13), dRaw58 = dirArrayFor(cand, bars58, ctx58, S58);
    let chosen = null;
    for (const focus of ["PH", "RTH"]) {
      const d13 = focus === "PH" ? restrictPHADX(dRaw13, ctx13) : dRaw13;
      const d58 = focus === "PH" ? restrictPHADX(dRaw58, ctx58) : dRaw58;
      for (const s of STOPS) for (const t of TGTS) for (const cap of CAPS) for (const br of BRAKES) {
        const r13 = evalLedger(applyDaily(Lab.runLedger(bars13, buildSig(bars13, ctx13, d13, s, t)), cap, br));
        if (!(r13.feasible && r13.net$ > 0 && r13.n >= 3)) continue;
        const r58 = evalLedger(applyDaily(Lab.runLedger(bars58, buildSig(bars58, ctx58, d58, s, t)), cap, br));
        if (!(r58.feasible && r58.net$ > 0 && r58.n >= 5)) continue;
        const score = Math.min(r13.net$, r58.net$);   // reward the WEAKER sample → robustness
        if (!chosen || score > chosen.score) chosen = { focus, s, t, cap, br, r13, r58, score };
      }
    }
    best.push({ label: cand.label, chosen });
  }

  const winners = best.filter((b) => b.chosen).sort((a, b) => b.chosen.score - a.chosen.score);

  console.log(`@1 NQ ($20/pt) — best SURVIVING + profitable config per candidate (feasible & net+ on BOTH samples):\n`);
  const H = "Candidate".padEnd(31) + "Config(focus s/t cap brake)".padEnd(28) + "13dNet".padStart(8) + "Trd".padStart(4) + "58dNet".padStart(8) + "Trd".padStart(4) + "58dDD".padStart(7) + "58dWD".padStart(7);
  console.log(H); console.log("-".repeat(H.length));
  for (const b of winners) {
    const c = b.chosen;
    const cfg = `${c.focus} ${c.s}/${c.t} cap${c.cap} ${c.br ? "$" + c.br : "—"}`;
    console.log(b.label.slice(0, 30).padEnd(31) + cfg.padEnd(28) + dol(c.r13.net$).padStart(8) + String(c.r13.n).padStart(4) + dol(c.r58.net$).padStart(8) + String(c.r58.n).padStart(4) + ("-$" + c.r58.dd$).padStart(7) + ("-$" + c.r58.wd$).padStart(7));
  }
  const losers = best.filter((b) => !b.chosen).map((b) => b.label);
  console.log(`\nSurvived @1 NQ (feasible + net+ on both samples): ${winners.length}/${CANDIDATES.length}.`);
  if (losers.length) console.log(`No feasible+profitable 1-NQ config found for: ${losers.join(", ")}`);
  if (winners.length) { const top = winners[0].chosen; console.log(`\nBEST 1-NQ SURVIVOR -> ${winners[0].label}: ${top.focus} stop ${top.s}xATR / tgt ${top.t}xATR, ${top.cap} trade(s)/day${top.br ? ", daily brake $" + top.br : ""}.`);
    console.log(`   13d ${dol(top.r13.net$)} (${top.r13.n}t, ${top.r13.win}%, PF ${top.r13.pf})  |  58d ${dol(top.r58.net$)} (${top.r58.n}t, ${top.r58.win}%, PF ${top.r58.pf}, maxDD -$${top.r58.dd$}, worstDay -$${top.r58.wd$}, maxLossStreak ${top.r58.mls}).`); }

  fs.writeFileSync(OUT_JSON, JSON.stringify({ generatedAt: new Date().toISOString(), sizing: "1 NQ ($20/pt)", span13, span58, winners: winners.map((w) => ({ label: w.label, ...w.chosen })) }, null, 2));
  const md = [];
  md.push(`# Survive-1NQ — best surviving + profitable strategy at 1 NQ ($20/pt) (${new Date().toISOString().slice(0, 10)})`);
  md.push(`\n1 NQ = $20/pt = 2× live size, so the Combine walls bite twice as hard (feasible = worst day < $${DLL} AND maxDD < $${MLL}). Searched the catalog13 top-10 + champion + the Three-inside+Pin-bar merge, each across focus×stop×target×cap×brake. A candidate survives only if feasible AND net-positive on BOTH the 13-day and 58-day charts @1 NQ. Dollars @1 NQ. Gross only.`);
  md.push(`\n**Survived @1 NQ: ${winners.length}/${CANDIDATES.length}.**`);
  if (winners.length) {
    md.push(`\n## Surviving 1-NQ configs (ranked by weaker-sample net = robustness)\n`);
    md.push(`| Candidate | Config | 13d Net | 13d Trd | 58d Net | 58d Trd | 58d maxDD | 58d worstDay | 58d Win/PF |`);
    md.push(`|-----------|--------|------:|--:|------:|--:|------:|------:|:--:|`);
    for (const b of winners) { const c = b.chosen; md.push(`| ${b.label} | ${c.focus} ${c.s}/${c.t} cap${c.cap}${c.br ? " $" + c.br : ""} | ${dol(c.r13.net$)} | ${c.r13.n} | ${dol(c.r58.net$)} | ${c.r58.n} | -$${c.r58.dd$} | -$${c.r58.wd$} | ${c.r58.win}%/${c.r58.pf} |`); }
    const top = winners[0].chosen;
    md.push(`\n### Best 1-NQ survivor: **${winners[0].label}**`);
    md.push(`- Config: **${top.focus}**, stop **${top.s}×ATR**, target **${top.t}×ATR**, **${top.cap} trade(s)/day**${top.br ? `, daily brake **$${top.br}**` : ""}.`);
    md.push(`- 13d: ${dol(top.r13.net$)} (${top.r13.n}t, ${top.r13.win}%, PF ${top.r13.pf}). 58d: ${dol(top.r58.net$)} (${top.r58.n}t, ${top.r58.win}%, PF ${top.r58.pf}), maxDD -$${top.r58.dd$}, worstDay -$${top.r58.wd$}, maxLossStreak ${top.r58.mls}.`);
  }
  if (losers.length) md.push(`\nNo feasible+profitable 1-NQ config found for: ${losers.join(", ")}.`);
  md.push(`\n> Caveat: feasible @1 NQ means a thin survival margin — one bad streak past the backtest can still breach the $2000 trailing wall, because 1 NQ doubles every swing. 5 MNQ remains the safer collectable size; this is an exploration of whether 1 NQ is survivable at all. DATA-ONLY: champion locked, nothing live touched.`);
  fs.writeFileSync(OUT_MD, md.join("\n") + "\n");

  console.log(`\nSaved ${OUT_JSON} and ${OUT_MD}. (${((Date.now() - t0) / 1000).toFixed(1)}s)  DATA-ONLY: champion locked.`);
}

main();
