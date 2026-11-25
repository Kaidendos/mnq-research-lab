// =============================================================
//  survive1nq2.js — DEEPER 1-NQ optimization (round 2 of survive1nq.js).
//
//  Round 1 found 4 survivors at 1 NQ ($20/pt) using a coarse grid + 2 samples.
//  Round 2 turns the screws:
//    (1) FINER bracket grid around the winning zone.
//    (2) TWO new tuning dims: ADX threshold {20,25} and entry-window width
//        {tight 15:00-15:45, wide 14:30-16:00}.
//    (3) THREE samples now — 13d, 58d, AND the 89-day MNQ CSV. A config counts
//        ONLY if it is Combine-feasible AND net-positive on ALL THREE. (Price is
//        identical NQ vs MNQ; only $/pt differs, so the 89d series is valid here.)
//  Scored by the WEAKEST sample's net (min across 3) = anti-overfit ranking.
//
//  Reuses catalog13/lab-new4 — zero strategy reimplementation.
//  DATA-ONLY / TopStep-compliant: never places an order. Champion stays locked.
//  Run:  node survive1nq2.js
// =============================================================
"use strict";

const fs = require("fs");
const path = require("path");
require("./public/indicators.js");
const Lab = require("./lab-new4");
const Cat = require("./catalog13");

const PV = 20;                          // $/pt @ 1 NQ
const DLL = Lab.DLL, MLL = Lab.MLL;     // 1000 / 2000
const CSV_90 = "C:\\Users\\kaide\\Downloads\\CME_MINI_DL_MNQ1!, 5 (1).csv";
const OUT_JSON = path.join(__dirname, "logs", "survive1nq2-results.json");
const OUT_MD = path.join(__dirname, "logs", "survive1nq2-report.md");

// finer grid + new dims
const STOPS = [0.5, 0.6, 0.7, 0.8, 1.0];
const TGTS = [1.5, 2.0, 2.5, 3.0];
const ADXS = [20, 25];
const WINDOWS = [[900, 945], [870, 960]];   // tight (15:00-15:45) | wide (14:30-16:00)
const CAPS = [1, 2];
const BRAKES = [0, 500];

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
  else if (cand.kind === "merge") {
    const ti = new Array(bars.length).fill(0); const fn = NEWMAP.get("n44_threeInside");
    for (let i = 210; i < bars.length; i++) { try { ti[i] = fn(ctx, i) || 0; } catch (e) { ti[i] = 0; } }
    const pb = S["pinBar"];
    for (let i = 210; i < bars.length; i++) { if (ti[i] === 0) continue; for (let j = Math.max(0, i - 3); j <= i; j++) { const d = pb[j] ? pb[j].dir : 0; if (d === ti[i]) { a[i] = ti[i]; break; } } }
  }
  return a;
}
// focus: null = full RTH (no PH/ADX gate); else {adx, lo, hi}
function applyFocus(dir, ctx, focus) {
  if (!focus) return dir;
  return dir.map((d, i) => (d !== 0 && ctx.mins[i] >= focus.lo && ctx.mins[i] <= focus.hi && ctx.adx && ctx.adx[i] != null && ctx.adx[i] > focus.adx) ? d : 0);
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

// Build the list of focus variants to try (PH variants + one RTH)
function focusVariants() {
  const out = [{ tag: "RTH", focus: null }];
  for (const adx of ADXS) for (const w of WINDOWS) out.push({ tag: `PH${adx}/${w[0] === 900 ? "tight" : "wide"}`, focus: { adx, lo: w[0], hi: w[1] } });
  return out;
}

function bestConfigForSample(dirRaw, bars, ctx, fv) {
  // returns map keyed by configId -> result, for one sample
  const res = new Map();
  for (const v of fv) {
    const d = applyFocus(dirRaw, ctx, v.focus);
    for (const s of STOPS) for (const t of TGTS) {
      const base = Lab.runLedger(bars, buildSig(bars, ctx, d, s, t));
      for (const cap of CAPS) for (const br of BRAKES) {
        const r = evalLedger(applyDaily(base, cap, br));
        res.set(`${v.tag}|${s}|${t}|${cap}|${br}`, { v, s, t, cap, br, r });
      }
    }
  }
  return res;
}

function main() {
  const t0 = Date.now();
  const bars13 = Lab.loadCsv(Lab.CSV_13);
  const bars58 = loadJson(path.join(__dirname, "data", "nq-5m.json"));
  const bars90 = Lab.loadCsv(CSV_90);
  const span13 = spanOf(bars13), span58 = spanOf(bars58), span90 = spanOf(bars90);
  const ctx13 = Cat.ctxOf(bars13), S13 = Lab.buildAll(bars13);
  const ctx58 = Cat.ctxOf(bars58), S58 = Lab.buildAll(bars58);
  const ctx90 = Cat.ctxOf(bars90), S90 = Lab.buildAll(bars90);
  const fv = focusVariants();

  console.log(`SURVIVE-1NQ-2 — deeper optimization, TRIPLE out-of-sample (must be feasible+net+ on ALL 3). $20/pt.`);
  console.log(`13d ${span13[0]}->${span13[1]} | 58d ${span58[0]}->${span58[1]} | 89d ${span90[0]}->${span90[1]}`);
  console.log(`grid: focus{RTH + PH(adx${JSON.stringify(ADXS)} x win[tight,wide])} x stop${JSON.stringify(STOPS)} x tgt${JSON.stringify(TGTS)} x cap${JSON.stringify(CAPS)} x brake${JSON.stringify(BRAKES)} = ${fv.length * STOPS.length * TGTS.length * CAPS.length * BRAKES.length} cfg/candidate\n`);

  const best = [];
  for (const cand of CANDIDATES) {
    const m13 = bestConfigForSample(dirArrayFor(cand, bars13, ctx13, S13), bars13, ctx13, fv);
    const m58 = bestConfigForSample(dirArrayFor(cand, bars58, ctx58, S58), bars58, ctx58, fv);
    const m90 = bestConfigForSample(dirArrayFor(cand, bars90, ctx90, S90), bars90, ctx90, fv);
    let chosen = null;
    for (const [id, c13] of m13) {
      const c58 = m58.get(id), c90 = m90.get(id);
      if (!c58 || !c90) continue;
      const ok = [c13.r, c58.r, c90.r].every((r) => r.feasible && r.net$ > 0);
      if (!ok) continue;
      if (!(c13.r.n >= 3 && c58.r.n >= 5 && c90.r.n >= 8)) continue;   // require real samples
      const score = Math.min(c13.r.net$, c58.r.net$, c90.r.net$);
      if (!chosen || score > chosen.score) chosen = { id, v: c13.v, s: c13.s, t: c13.t, cap: c13.cap, br: c13.br, r13: c13.r, r58: c58.r, r90: c90.r, score };
    }
    best.push({ label: cand.label, chosen });
    process.stdout.write(`  ${cand.label.padEnd(30)} ${chosen ? "survives (min-net " + dol(chosen.score) + ")" : "no triple-feasible config"}\n`);
  }

  const winners = best.filter((b) => b.chosen).sort((a, b) => b.chosen.score - a.chosen.score);
  console.log(`\n@1 NQ — survivors feasible + net+ on ALL THREE samples (ranked by weakest-sample net):\n`);
  const H = "Candidate".padEnd(28) + "Config".padEnd(26) + "13dNet".padStart(8) + "58dNet".padStart(8) + "89dNet".padStart(8) + "89dDD".padStart(7) + "89dWD".padStart(7);
  console.log(H); console.log("-".repeat(H.length));
  for (const b of winners) {
    const c = b.chosen;
    const cfg = `${c.v.tag} ${c.s}/${c.t} c${c.cap}${c.br ? "/$" + c.br : ""}`;
    console.log(b.label.slice(0, 27).padEnd(28) + cfg.padEnd(26) + dol(c.r13.net$).padStart(8) + dol(c.r58.net$).padStart(8) + dol(c.r90.net$).padStart(8) + ("-$" + c.r90.dd$).padStart(7) + ("-$" + c.r90.wd$).padStart(7));
  }
  const losers = best.filter((b) => !b.chosen).map((b) => b.label);
  console.log(`\nTriple-sample survivors: ${winners.length}/${CANDIDATES.length}.`);
  if (losers.length) console.log(`No triple-feasible config: ${losers.join(", ")}`);
  if (winners.length) {
    const top = winners[0].chosen;
    console.log(`\nBEST 1-NQ SURVIVOR (round 2) -> ${winners[0].label}: ${top.v.tag}, stop ${top.s}xATR / tgt ${top.t}xATR, ${top.cap} trade(s)/day${top.br ? ", brake $" + top.br : ""}.`);
    console.log(`   13d ${dol(top.r13.net$)} (${top.r13.n}t) | 58d ${dol(top.r58.net$)} (${top.r58.n}t) | 89d ${dol(top.r90.net$)} (${top.r90.n}t, ${top.r90.win}%, PF ${top.r90.pf}, maxDD -$${top.r90.dd$}, worstDay -$${top.r90.wd$}, maxLossStreak ${top.r90.mls}).`);
  }

  fs.writeFileSync(OUT_JSON, JSON.stringify({ generatedAt: new Date().toISOString(), sizing: "1 NQ ($20/pt)", span13, span58, span90, winners: winners.map((w) => ({ label: w.label, ...w.chosen })) }, null, 2));
  const md = [];
  md.push(`# Survive-1NQ round 2 — deeper optimization, triple out-of-sample (${new Date().toISOString().slice(0, 10)})`);
  md.push(`\nRound 2 of the 1-NQ ($20/pt) hunt: finer bracket grid + two new tuning dims (ADX threshold {${ADXS.join(",")}}, entry window {tight 15:00-15:45, wide 14:30-16:00}), and a **third** out-of-sample chart (the 89-day MNQ CSV). A config counts only if it is Combine-feasible (worst day < $${DLL} AND maxDD < $${MLL}) AND net-positive on **all three** samples. Ranked by the weakest sample's net (anti-overfit). Dollars @1 NQ, gross.`);
  md.push(`\n13d ${span13[0]}->${span13[1]} | 58d ${span58[0]}->${span58[1]} | 89d ${span90[0]}->${span90[1]}.`);
  md.push(`\n**Triple-sample survivors: ${winners.length}/${CANDIDATES.length}.**`);
  if (winners.length) {
    md.push(`\n## Survivors (feasible + net+ on 13d AND 58d AND 89d)\n`);
    md.push(`| Candidate | Config | 13d Net | 58d Net | 89d Net | 89d Trd | 89d maxDD | 89d worstDay | 89d Win/PF |`);
    md.push(`|-----------|--------|------:|------:|------:|--:|------:|------:|:--:|`);
    for (const b of winners) { const c = b.chosen; md.push(`| ${b.label} | ${c.v.tag} ${c.s}/${c.t} cap${c.cap}${c.br ? " $" + c.br : ""} | ${dol(c.r13.net$)} | ${dol(c.r58.net$)} | ${dol(c.r90.net$)} | ${c.r90.n} | -$${c.r90.dd$} | -$${c.r90.wd$} | ${c.r90.win}%/${c.r90.pf} |`); }
    const top = winners[0].chosen;
    md.push(`\n### Best round-2 survivor: **${winners[0].label}**`);
    md.push(`- Config: **${top.v.tag}**, stop **${top.s}×ATR**, target **${top.t}×ATR**, **${top.cap} trade(s)/day**${top.br ? `, daily brake **$${top.br}**` : ""}.`);
    md.push(`- 13d ${dol(top.r13.net$)} (${top.r13.n}t) · 58d ${dol(top.r58.net$)} (${top.r58.n}t) · 89d ${dol(top.r90.net$)} (${top.r90.n}t, ${top.r90.win}%, PF ${top.r90.pf}), maxDD -$${top.r90.dd$}, worstDay -$${top.r90.wd$}, maxLossStreak ${top.r90.mls}.`);
  }
  if (losers.length) md.push(`\nNo config feasible+profitable on all three samples for: ${losers.join(", ")}.`);
  md.push(`\n> Caveat unchanged: 1 NQ doubles every swing. Surviving three backtests is a stronger signal than two, but a future streak worse than the sample can still breach the $2000 trailing wall. 5 MNQ remains the safer collectable size. DATA-ONLY: champion locked, nothing live touched.`);
  fs.writeFileSync(OUT_MD, md.join("\n") + "\n");

  console.log(`\nSaved ${OUT_JSON} and ${OUT_MD}. (${((Date.now() - t0) / 1000).toFixed(1)}s)  DATA-ONLY: champion locked.`);
}

main();
