// =============================================================
//  backtest-compare.js — replay BOTH keeper strategies over the same
//  ProjectX 5-min history and report which actually made money:
//    - ORB v5      (orb.js)      — first strong break of the opening range
//    - mean-rev v1.1 (meanrev.js) — fade band stretch back to the mean
//
//  Same exit sim for both (bar-by-bar; stop = signal stop, target = signal
//  target; conservative on ties -> stop; mark-to-close at RTH end). One
//  position at a time per strategy. ProjectX-only feed (no Yahoo).
//
//  DATA-ONLY / TopStep-compliant: reads history, never places an order.
//
//  Run:  node backtest-compare.js            (print)
//        node backtest-compare.js --post     (also send a card to Discord)
//
//  Consumes bars = [{ t, o, h, l, c, v }], t = epoch SECONDS, ascending.
// =============================================================
"use strict";

require("./public/indicators.js");
require("./public/meanrev.js");
require("./public/orb.js");
const MeanRev = globalThis.MeanRev;
const ORB = globalThis.ORB;
const ProjectX = require("./projectx.js");

const PV_MNQ = ORB.CONFIG.pointValueMNQ; // $2 / pt

function getWebhook() {
  if (process.env.DISCORD_WEBHOOK_URL) return process.env.DISCORD_WEBHOOK_URL;
  try { return require("./secrets.local.js").discordWebhook; } catch { return null; }
}
function dayKeyOf(epochSec) {
  const et = new Date(new Date(epochSec * 1000).toLocaleString("en-US", { timeZone: "America/New_York" }));
  return `${et.getFullYear()}-${et.getMonth()}-${et.getDate()}`;
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

// Walk forward from entryIdx to the day's end. Returns P&L points + exit info.
function simulateTrade(bars, entryIdx, sig) {
  const dayKey = dayKeyOf(bars[entryIdx].t);
  const isLong = sig.dir === 1;
  for (let k = entryIdx + 1; k < bars.length; k++) {
    if (dayKeyOf(bars[k].t) !== dayKey) break; // flat by EOD
    const b = bars[k];
    const hitStop = isLong ? b.l <= sig.stop : b.h >= sig.stop;
    const hitTgt = isLong ? b.h >= sig.target : b.l <= sig.target;
    if (hitStop) return { pts: isLong ? sig.stop - sig.entry : sig.entry - sig.stop, exit: "stop", exitIdx: k };
    if (hitTgt) return { pts: isLong ? sig.target - sig.entry : sig.entry - sig.target, exit: "target", exitIdx: k };
  }
  let last = entryIdx;
  for (let k = entryIdx + 1; k < bars.length && dayKeyOf(bars[k].t) === dayKey; k++) last = k;
  const px = bars[last].c;
  return { pts: isLong ? px - sig.entry : sig.entry - px, exit: "close", exitIdx: last };
}

function tally(trades) {
  const wins = trades.filter((t) => t.pts > 0);
  const losses = trades.filter((t) => t.pts <= 0);
  const grossWin = wins.reduce((s, t) => s + t.pts, 0);
  const grossLoss = Math.abs(losses.reduce((s, t) => s + t.pts, 0));
  const netPts = trades.reduce((s, t) => s + t.pts, 0);
  return {
    trades, n: trades.length, wins: wins.length, losses: losses.length,
    winRate: trades.length ? (wins.length / trades.length) * 100 : 0,
    netPts, netUSD: netPts * PV_MNQ,
    pf: grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? Infinity : 0),
  };
}

// ORB: first strong break per day, only inside the 09:45-10:30 entry window.
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
      break;
    }
  }
  return tally(trades);
}

// Mean-rev: scan every closed bar; enter on a reclaim signal when flat,
// then jump past the exit bar before scanning again.
function runMeanRev(bars) {
  const trades = [];
  let i = 1;
  while (i < bars.length) {
    const sig = MeanRev.computeMeanRev(bars, i);
    if (sig.signal === "BUY" || sig.signal === "SELL") {
      const res = simulateTrade(bars, i, sig);
      trades.push({ date: etDate(bars[i].t), dir: sig.signal, pts: res.pts, exit: res.exit });
      i = res.exitIdx + 1; // no overlapping positions
    } else {
      i++;
    }
  }
  return tally(trades);
}

function line(name, r) {
  return `${name.padEnd(22)} ${String(r.n).padStart(3)} tr  ${String(r.wins + "W/" + r.losses + "L").padStart(8)}  win ${fmt(r.winRate, 0).padStart(3)}%  PF ${(r.pf === Infinity ? "inf" : fmt(r.pf, 2)).padStart(5)}  net ${money(r.netUSD).padStart(8)}/MNQ`;
}

function buildEmbed(mr, orbOn, orbOff, meta) {
  const ranked = [
    { name: "Mean-rev v1.1", r: mr },
    { name: "ORB v5 (filter ON)", r: orbOn },
    { name: "ORB v5 (filter OFF)", r: orbOff },
  ].sort((a, b) => b.r.netUSD - a.r.netUSD);
  const winner = ranked[0];
  return {
    content: "🏁 **Strategy shootout** — which keeper actually won? (ProjectX data)",
    allowed_mentions: { parse: [] },
    embeds: [{
      title: `Mean-rev v1.1  vs  ORB v5 · ${meta.days}-day ProjectX replay`,
      description:
        `Same exit sim for both (stop/target from the signal, flat by EOD, 1 MNQ). This window is the **choppy June regime** (ADX low, ranges wide) — read accordingly.`,
      color: winner.r.netUSD >= 0 ? 0x2ecc71 : 0xe74c3c,
      fields: [
        { name: "Mean-rev v1.1", value: `${mr.n} trades · ${mr.wins}W/${mr.losses}L · win ${fmt(mr.winRate, 0)}% · PF ${mr.pf === Infinity ? "∞" : fmt(mr.pf, 2)} · **${money(mr.netUSD)}/MNQ**`, inline: false },
        { name: "ORB v5 (filter ON = live)", value: `${orbOn.n} trades · **${money(orbOn.netUSD)}/MNQ**`, inline: false },
        { name: "ORB v5 (filter OFF)", value: `${orbOff.n} trades · ${orbOff.wins}W/${orbOff.losses}L · win ${fmt(orbOff.winRate, 0)}% · **${money(orbOff.netUSD)}/MNQ**`, inline: false },
        { name: "🏆 Winner this regime", value: `**${winner.name}** (${money(winner.r.netUSD)}/MNQ)`, inline: false },
      ],
      footer: { text: "Backtest · ProjectX 5-min · 1 MNQ · data-only, no orders · TopStep-compliant" },
    }],
  };
}

(async () => {
  const doPost = process.argv.includes("--post");
  const bars = await getBars();
  const days = new Set(bars.map((b) => dayKeyOf(b.t))).size;
  console.log(`Comparing over ${bars.length} bars / ${days} ET days (ProjectX sim), 1 MNQ.\n`);

  const mr = runMeanRev(bars);
  const orbOn = runORB(bars, { useRangeFilter: true, maxRangePts: 70 });
  const orbOff = runORB(bars, { useRangeFilter: false });

  console.log(line("mean-rev v1.1", mr));
  console.log(line("ORB v5 (filter ON)", orbOn));
  console.log(line("ORB v5 (filter OFF)", orbOff));

  if (doPost) {
    await (async (payload) => {
      const hook = getWebhook();
      if (!hook) throw new Error("no webhook");
      const r = await fetch(hook, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!r.ok) throw new Error("discord " + r.status + " " + (await r.text()));
    })(buildEmbed(mr, orbOn, orbOff, { days }));
    console.log("\nPosted comparison to Discord.");
  }
})().catch((e) => { console.error("compare error:", e.message); process.exit(1); });
