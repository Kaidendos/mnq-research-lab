// =============================================================
//  backtest-orb.js — replay past 5-min bars through ORB v5 and simulate the
//  OCO bracket exit (stop = opposite side of the opening range, target =
//  1.5R), bar-by-bar, to see whether you'd be net up or down. Posts a
//  results card to Discord.
//
//  This is DATA-ONLY and TopStep-compliant: it reads history (ProjectX
//  sim feed, else Yahoo) and posts a webhook. It never places an order.
//
//  Exit model (one bar = 5 min; intrabar order of H/L unknown, so we are
//  conservative — if a bar's range touches BOTH stop and target, we count
//  the STOP as hit first). If neither is hit by RTH close, we mark the
//  trade out at the day's last close.
//
//  Run:  node backtest-orb.js              (range filter OFF — see every break)
//        ORB_RANGE_FILTER=on node backtest-orb.js
//        node backtest-orb.js --no-post    (print only, don't touch Discord)
//
//  Consumes bars = [{ t, o, h, l, c, v }], t = epoch SECONDS, ascending.
// =============================================================
"use strict";

require("./public/indicators.js");
require("./public/orb.js");
const ORB = globalThis.ORB;
const ProjectX = require("./projectx.js");

const SYMBOL = process.env.SYMBOL || "NQ=F";
const PV_MNQ = ORB.CONFIG.pointValueMNQ; // $2 / pt
const PV_NQ = ORB.CONFIG.pointValueNQ;   // $20 / pt

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

// ProjectX-only history (real-time TopstepX sim feed). The U26 contract has
// a shallow history (~14 days), so the sample is small but it's the exact
// data the live watcher uses.
async function getBars() {
  const bars = await ProjectX.fetchBars({ unitNumber: 5, lookbackDays: 60 });
  if (!bars.length) throw new Error("ProjectX returned 0 bars");
  return { bars, feed: "ProjectX sim" };
}

// Simulate the OCO bracket for one trade. Returns P&L in points (+win / -loss).
function simulateTrade(bars, entryIdx, sig) {
  const dayKey = dayKeyOf(bars[entryIdx].t);
  const isLong = sig.dir === 1;
  for (let k = entryIdx + 1; k < bars.length; k++) {
    if (dayKeyOf(bars[k].t) !== dayKey) break; // don't hold overnight
    const b = bars[k];
    const hitStop = isLong ? b.l <= sig.stop : b.h >= sig.stop;
    const hitTgt = isLong ? b.h >= sig.target : b.l <= sig.target;
    if (hitStop) return { pts: isLong ? sig.stop - sig.entry : sig.entry - sig.stop, exit: "stop", bars: k - entryIdx };
    if (hitTgt) return { pts: isLong ? sig.target - sig.entry : sig.entry - sig.target, exit: "target", bars: k - entryIdx };
  }
  // Neither hit by day end -> mark out at last same-day close.
  let last = entryIdx;
  for (let k = entryIdx + 1; k < bars.length && dayKeyOf(bars[k].t) === dayKey; k++) last = k;
  const px = bars[last].c;
  return { pts: isLong ? px - sig.entry : sig.entry - px, exit: "close", bars: last - entryIdx };
}

function runBacktest(bars, opts) {
  const trades = [];
  // computeORB re-scans the whole ET day on each call (costly timezone math),
  // and a signal can only fire inside the entry window (orEnd..entryEnd). So
  // group bars by day and only evaluate the handful of in-window bars, and
  // stop a day as soon as its first break fires. ~100 calls instead of 1000s.
  const C = ORB.CONFIG;
  const orEnd = ORB.hhmmToMins(C.openHHMM) + C.orMinutes;
  const entryEnd = ORB.hhmmToMins(C.entryEndHHMM);

  const byDay = new Map();
  for (let i = 0; i < bars.length; i++) {
    const key = dayKeyOf(bars[i].t);
    if (!byDay.has(key)) byDay.set(key, []);
    byDay.get(key).push(i);
  }

  for (const idxs of byDay.values()) {
    for (const i of idxs) {
      const mins = ORB.etParts(bars[i].t).mins;
      if (mins < orEnd || mins >= entryEnd) continue; // only the entry window
      const sig = ORB.computeORB(bars, i, opts);
      if (sig.signal !== "BUY" && sig.signal !== "SELL") continue;
      const res = simulateTrade(bars, i, sig);
      trades.push({
        date: etDate(bars[i].t), dir: sig.signal, entry: sig.entry,
        stop: sig.stop, target: sig.target, orRange: sig.orRange,
        pts: res.pts, exit: res.exit, heldBars: res.bars,
      });
      break; // first break of the day only (matches v5 / orb.js)
    }
  }
  const wins = trades.filter((t) => t.pts > 0);
  const losses = trades.filter((t) => t.pts <= 0);
  const grossWin = wins.reduce((s, t) => s + t.pts, 0);
  const grossLoss = Math.abs(losses.reduce((s, t) => s + t.pts, 0));
  const netPts = trades.reduce((s, t) => s + t.pts, 0);
  return {
    trades, n: trades.length, wins: wins.length, losses: losses.length,
    winRate: trades.length ? (wins.length / trades.length) * 100 : 0,
    netPts, grossWin, grossLoss,
    pf: grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? Infinity : 0),
  };
}

function fmt(x, d = 2) { return x == null ? "—" : Number(x).toFixed(d); }
function money(x) { return (x >= 0 ? "+$" : "-$") + Math.abs(x).toFixed(0); }

async function postDiscord(payload) {
  const hook = getWebhook();
  if (!hook) throw new Error("no webhook — set DISCORD_WEBHOOK_URL or secrets.local.js");
  const r = await fetch(hook, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error("discord " + r.status + " " + (await r.text()));
}

function buildEmbed(off, on, meta) {
  const netMNQ = off.netPts * PV_MNQ;
  const netNQ5 = off.netPts * PV_NQ * 5; // the 5-NQ size you were running
  const up = off.netPts >= 0;
  const tradeLines = off.trades.length
    ? off.trades.map((t) =>
        `\`${t.date}\` ${t.dir === "BUY" ? "▲L" : "▼S"}  ${t.pts >= 0 ? "✅" : "❌"} ${t.pts >= 0 ? "+" : ""}${fmt(t.pts, 1)}pt (${t.exit})  ·  OR ${fmt(t.orRange, 0)}pt`
      ).slice(0, 12).join("\n")
    : "_no trades in window_";

  return {
    content: "📊 **ORB v5 backtest** — would you be up or down?",
    allowed_mentions: { parse: [] },
    embeds: [{
      title: `ORB v5 · ${meta.days}-day replay · NQ 5-min`,
      description:
        `Replayed **${meta.barCount}** bars (${meta.feed}). Exit model = OCO bracket: stop at the opposite side of the opening range, target at **1.5R**, conservative on ties (stop wins).\n\n` +
        `⚠️ This window is the **wild June regime** — most opening ranges were >70pt, so v5's range filter would have **skipped them**. Read this as a *mechanics check*, not the real long-run edge (that needs the TradingView Jan–Jun sample).`,
      color: up ? 0x2ecc71 : 0xe74c3c,
      fields: [
        { name: "Trades", value: `${off.n}  (${off.wins}W / ${off.losses}L)`, inline: true },
        { name: "Win rate", value: `${fmt(off.winRate, 0)}%`, inline: true },
        { name: "Profit factor", value: off.pf === Infinity ? "∞" : fmt(off.pf, 2), inline: true },
        { name: "Net (per 1 MNQ — recommended size)", value: `${money(netMNQ)}  (${fmt(off.netPts, 1)} pt)`, inline: false },
        { name: "Net (per 5 NQ — what you were trading) ⚠️", value: `${money(netNQ5)}  — 50× the swing`, inline: false },
        { name: "With range filter ON (the live setting)", value: `${on.n} trades — v5 stands down in this regime`, inline: false },
        { name: "Trade-by-trade", value: tradeLines, inline: false },
      ],
      footer: { text: "Backtest only · 5-min bars (intrabar order unknown) · data-only, no orders placed · TopStep-compliant" },
    }],
  };
}

(async () => {
  const noPost = process.argv.includes("--no-post");
  const { bars, feed } = await getBars();
  if (bars.length < 50) { console.error(`only ${bars.length} bars — not enough to backtest`); return; }

  const dayCount = new Set(bars.map((b) => dayKeyOf(b.t))).size;
  const off = runBacktest(bars, { useRangeFilter: false });
  const on = runBacktest(bars, { useRangeFilter: true, maxRangePts: 70 });

  console.log(`Backtest over ${bars.length} bars / ${dayCount} ET days (${feed}).`);
  console.log(`Filter OFF: ${off.n} trades, ${off.wins}W/${off.losses}L, win ${fmt(off.winRate, 0)}%, PF ${off.pf === Infinity ? "inf" : fmt(off.pf, 2)}, net ${fmt(off.netPts, 1)}pt = ${money(off.netPts * PV_MNQ)}/MNQ, ${money(off.netPts * PV_NQ * 5)}/5NQ`);
  console.log(`Filter ON:  ${on.n} trades`);
  for (const t of off.trades) {
    console.log(`  ${t.date} ${t.dir} entry ${fmt(t.entry)} stop ${fmt(t.stop)} -> ${t.exit} ${fmt(t.pts, 1)}pt (OR ${fmt(t.orRange, 0)}pt)`);
  }

  if (noPost) { console.log("--no-post: skipped Discord."); return; }
  await postDiscord(buildEmbed(off, on, { days: dayCount, barCount: bars.length, feed }));
  console.log("Posted backtest result to Discord.");
})().catch((e) => { console.error("backtest error:", e.message); process.exit(1); });
