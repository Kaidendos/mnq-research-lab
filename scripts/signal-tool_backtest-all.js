// =============================================================
//  backtest-all.js — replay EVERY TradingView strategy family over the same
//  ProjectX 5-min history and rank them, reported per 1 MNQ ($2/pt) AND per
//  1 NQ ($20/pt):
//    - Simple Strategy : v5 (60/32), v3 (50/50), v5-loose   (simple.js)
//    - ORB v5          : filter ON (live) and OFF           (orb.js)
//    - Mean-rev v1.1    : band-fade to the mean             (meanrev.js)
//
//  One unified exit sim: bar-by-bar, stop = signal stop, target = signal
//  target, conservative on ties (stop first), flat by EOD. If the signal
//  carries useBE (the Simple Strategy), the stop latches to breakeven once
//  +1R is reached. One position at a time per strategy.
//
//  DATA-ONLY / TopStep-compliant: reads history, never places an order.
//
//  Run:  node backtest-all.js          (print)
//        node backtest-all.js --post    (also send a card to Discord)
//
//  Consumes bars = [{ t, o, h, l, c, v }], t = epoch SECONDS, ascending.
// =============================================================
"use strict";

require("./public/indicators.js");
require("./public/simple.js");
require("./public/orb.js");
require("./public/meanrev.js");
const Simple = globalThis.Simple;
const ORB = globalThis.ORB;
const MeanRev = globalThis.MeanRev;
const ProjectX = require("./projectx.js");

const PV_MNQ = Simple.CONFIG.pointValueMNQ; // $2 / pt
const PV_NQ = Simple.CONFIG.pointValueNQ;   // $20 / pt
const dayKeyOf = Simple.dayKeyOf;

function getWebhook() {
  if (process.env.DISCORD_WEBHOOK_URL) return process.env.DISCORD_WEBHOOK_URL;
  try { return require("./secrets.local.js").discordWebhook; } catch { return null; }
}
function etDate(epochSec) {
  return new Date(epochSec * 1000).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" });
}
function fmt(x, d = 2) { return x == null ? "—" : Number(x).toFixed(d); }
function money(x) { return (x >= 0 ? "+$" : "-$") + Math.abs(x).toFixed(0); }

async function getBars() {
  const bars = await ProjectX.fetchBars({ unitNumber: 5, lookbackDays: 60 });
  if (!bars.length) throw new Error("ProjectX returned 0 bars");
  return bars;
}

// Unified exit sim. Honors sig.useBE (Simple Strategy breakeven latch); for
// signals without it (ORB / mean-rev) the stop stays fixed.
function simulateTrade(bars, entryIdx, sig) {
  const dayKey = dayKeyOf(bars[entryIdx].t);
  const isLong = sig.dir === 1;
  const entry = sig.entry;
  let beLatched = false;
  for (let k = entryIdx + 1; k < bars.length; k++) {
    if (dayKeyOf(bars[k].t) !== dayKey) break; // flat by EOD
    const b = bars[k];
    const stopLvl = (sig.useBE && beLatched) ? entry : sig.stop;
    const hitStop = isLong ? b.l <= stopLvl : b.h >= stopLvl;
    const hitTgt = isLong ? b.h >= sig.target : b.l <= sig.target;
    if (hitStop) {
      const pts = isLong ? stopLvl - entry : entry - stopLvl;
      return { pts, exit: beLatched ? "be" : "stop", exitIdx: k };
    }
    if (hitTgt) {
      const pts = isLong ? sig.target - entry : entry - sig.target;
      return { pts, exit: "target", exitIdx: k };
    }
    if (sig.useBE && !beLatched) {
      const reached = isLong ? b.h >= entry + sig.beTrigPts : b.l <= entry - sig.beTrigPts;
      if (reached) beLatched = true;
    }
  }
  let last = entryIdx;
  for (let k = entryIdx + 1; k < bars.length && dayKeyOf(bars[k].t) === dayKey; k++) last = k;
  const px = bars[last].c;
  return { pts: isLong ? px - entry : entry - px, exit: "close", exitIdx: last };
}

function tally(trades) {
  const wins = trades.filter((t) => t.pts > 0);
  const losses = trades.filter((t) => t.pts <= 0);
  const grossWin = wins.reduce((s, t) => s + t.pts, 0);
  const grossLoss = Math.abs(losses.reduce((s, t) => s + t.pts, 0));
  const netPts = trades.reduce((s, t) => s + t.pts, 0);
  // worst peak-to-trough on the cumulative points curve (drawdown in points).
  let peak = 0, cum = 0, maxDD = 0;
  for (const t of trades) { cum += t.pts; peak = Math.max(peak, cum); maxDD = Math.max(maxDD, peak - cum); }
  return {
    trades, n: trades.length, wins: wins.length, losses: losses.length,
    winRate: trades.length ? (wins.length / trades.length) * 100 : 0,
    netPts, ddPts: maxDD,
    netMNQ: netPts * PV_MNQ, netNQ: netPts * PV_NQ,
    pf: grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? Infinity : 0),
  };
}

// --- Simple Strategy: scan every bar, daily-loss lockout, one position. ---
function runSimple(bars, opts) {
  const pre = Simple.prepare(bars, opts);
  const C = pre.C;
  const trades = [];
  let i = 1, curDay = null, dayPnLUSD = 0;
  while (i < bars.length) {
    const dk = dayKeyOf(bars[i].t);
    if (dk !== curDay) { curDay = dk; dayPnLUSD = 0; }
    if (dayPnLUSD <= -C.dayLoss) { i++; continue; }
    const sig = Simple.computeSimple(bars, i, opts, pre);
    if (sig.signal === "BUY" || sig.signal === "SELL") {
      const res = simulateTrade(bars, i, sig);
      trades.push({ date: etDate(bars[i].t), dir: sig.signal, pts: res.pts, exit: res.exit });
      dayPnLUSD += res.pts * PV_MNQ;
      i = res.exitIdx + 1;
    } else { i++; }
  }
  return tally(trades);
}

// --- ORB v5: first strong break per day, only inside the entry window. ---
function runORB(bars, opts) {
  const C = ORB.CONFIG;
  const orEnd = ORB.hhmmToMins(C.openHHMM) + C.orMinutes;
  const entryEnd = ORB.hhmmToMins(C.entryEndHHMM);
  const byDay = new Map();
  for (let i = 0; i < bars.length; i++) {
    const k = dayKeyOf(bars[i].t);
    if (!byDay.has(k)) byDay.set(k, []);
    byDay.get(k).push(i);
  }
  const trades = [];
  for (const idxs of byDay.values()) {
    for (const i of idxs) {
      const mins = ORB.etParts(bars[i].t).mins;
      if (mins < orEnd || mins >= entryEnd) continue;
      const sig = ORB.computeORB(bars, i, opts);
      if (sig.signal !== "BUY" && sig.signal !== "SELL") continue;
      const res = simulateTrade(bars, i, sig);
      trades.push({ date: etDate(bars[i].t), dir: sig.signal, pts: res.pts, exit: res.exit });
      break; // first break of the day only
    }
  }
  return tally(trades);
}

// --- Mean-rev v1.1: scan every bar, enter on reclaim, one position. ---
function runMeanRev(bars) {
  const trades = [];
  let i = 1;
  while (i < bars.length) {
    const sig = MeanRev.computeMeanRev(bars, i);
    if (sig.signal === "BUY" || sig.signal === "SELL") {
      const res = simulateTrade(bars, i, sig);
      trades.push({ date: etDate(bars[i].t), dir: sig.signal, pts: res.pts, exit: res.exit });
      i = res.exitIdx + 1;
    } else { i++; }
  }
  return tally(trades);
}

function line(name, r) {
  return `${name.padEnd(28)} ${String(r.n).padStart(3)} tr  ${String(r.wins + "W/" + r.losses + "L").padStart(8)}  win ${fmt(r.winRate, 0).padStart(3)}%  PF ${(r.pf === Infinity ? "inf" : fmt(r.pf, 2)).padStart(5)}  MNQ ${money(r.netMNQ).padStart(8)}  NQ ${money(r.netNQ).padStart(9)}  maxDD ${fmt(r.ddPts, 0)}pt`;
}

function buildEmbed(rows, meta) {
  const ranked = [...rows].sort((a, b) => b.r.netMNQ - a.r.netMNQ);
  const winner = ranked[0];
  return {
    content: "🏁 **Full strategy shootout** — every TradingView system on ProjectX data (MNQ & NQ)",
    allowed_mentions: { parse: [] },
    embeds: [{
      title: `Simple v5/v3/loose · ORB v5 · Mean-rev v1.1 · ${meta.days}-day ProjectX replay`,
      description:
        `Same exit sim for all, 1 contract, flat by EOD. **Net scales 10× from MNQ→NQ** (same points), so the ranking is identical — but NQ dollar risk is 10× too. ` +
        `This is the **choppy June regime** on a small ~${meta.days}-day sample (ADR approximated); a relative check, not the long-run edge.`,
      color: winner.r.netMNQ >= 0 ? 0x2ecc71 : 0xe74c3c,
      fields: ranked.map((row) => ({
        name: row.name,
        value: `${row.r.n} tr · ${row.r.wins}W/${row.r.losses}L · win ${fmt(row.r.winRate, 0)}% · PF ${row.r.pf === Infinity ? "∞" : fmt(row.r.pf, 2)} · MNQ **${money(row.r.netMNQ)}** / NQ **${money(row.r.netNQ)}**`,
        inline: false,
      })).concat([{ name: "🏆 Best this regime", value: `**${winner.name}** — MNQ ${money(winner.r.netMNQ)} / NQ ${money(winner.r.netNQ)}`, inline: false }]),
      footer: { text: "Backtest · ProjectX 5-min · 1 contract · data-only, no orders · TopStep-compliant" },
    }],
  };
}

(async () => {
  const doPost = process.argv.includes("--post");
  const bars = await getBars();
  const days = new Set(bars.map((b) => dayKeyOf(b.t))).size;
  console.log(`Full shootout over ${bars.length} bars / ${days} ET days (ProjectX). Net shown per 1 MNQ and per 1 NQ.\n`);

  const rows = [
    { name: Simple.PRESETS.v5.label, r: runSimple(bars, Simple.PRESETS.v5) },
    { name: Simple.PRESETS.v3.label, r: runSimple(bars, Simple.PRESETS.v3) },
    { name: Simple.PRESETS.v5loose.label, r: runSimple(bars, Simple.PRESETS.v5loose) },
    { name: "ORB v5 (filter ON = live)", r: runORB(bars, { useRangeFilter: true, maxRangePts: 70 }) },
    { name: "ORB v5 (filter OFF)", r: runORB(bars, { useRangeFilter: false }) },
    { name: "Mean-rev v1.1", r: runMeanRev(bars) },
  ];

  const ranked = [...rows].sort((a, b) => b.r.netMNQ - a.r.netMNQ);
  for (const row of ranked) console.log(line(row.name, row.r));

  if (doPost) {
    const payload = buildEmbed(rows, { days });
    const hook = getWebhook();
    if (!hook) throw new Error("no webhook — set DISCORD_WEBHOOK_URL or secrets.local.js");
    const r = await fetch(hook, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!r.ok) throw new Error("discord " + r.status + " " + (await r.text()));
    console.log("\nPosted full shootout to Discord.");
  }
})().catch((e) => { console.error("backtest-all error:", e.message); process.exit(1); });
