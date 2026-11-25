// =============================================================
//  backtest-simple.js — replay the 3 best "Simple Strategy" TradingView
//  versions (v5 BEST 60/32, v3 LOCKED 50/50, v5 looser 50/50) over the
//  same ProjectX 5-min history and report which made money.
//
//  Exit sim is faithful to the Pine: stop / target are a % of ADR, the stop
//  latches to BREAKEVEN once price reaches +1R, flat by EOD, daily-loss
//  lockout ($1000). Conservative on ties (stop checked before target).
//  One position at a time per version. ProjectX-only feed (no Yahoo).
//
//  DATA-ONLY / TopStep-compliant: reads history, never places an order.
//
//  Run:  node backtest-simple.js          (print)
//        node backtest-simple.js --post    (also send a card to Discord)
//
//  Consumes bars = [{ t, o, h, l, c, v }], t = epoch SECONDS, ascending.
// =============================================================
"use strict";

require("./public/indicators.js");
require("./public/simple.js");
const Simple = globalThis.Simple;
const ProjectX = require("./projectx.js");

const PV_MNQ = Simple.CONFIG.pointValueMNQ; // $2 / pt
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

// Walk forward from entryIdx to day end. Replicates the Pine exit: % -ADR
// stop / target, and a stop that latches to breakeven once +1R is reached.
// BE only takes effect on bars AFTER the trigger bar (conservative).
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
  return {
    trades, n: trades.length, wins: wins.length, losses: losses.length,
    winRate: trades.length ? (wins.length / trades.length) * 100 : 0,
    netPts, netUSD: netPts * PV_MNQ,
    pf: grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? Infinity : 0),
  };
}

// Replay one version. Scans every closed bar; on a signal when flat, takes
// the trade then jumps past the exit bar. Daily-loss lockout ($1000) and
// per-day reset are tracked just like the Pine.
function runVersion(bars, opts) {
  const pre = Simple.prepare(bars, opts);
  const C = pre.C;
  const trades = [];
  let i = 1;
  let curDay = null;
  let dayPnLUSD = 0;
  while (i < bars.length) {
    const dk = dayKeyOf(bars[i].t);
    if (dk !== curDay) { curDay = dk; dayPnLUSD = 0; } // new day -> reset lockout
    if (dayPnLUSD <= -C.dayLoss) { i++; continue; }   // locked out for the day
    const sig = Simple.computeSimple(bars, i, opts, pre);
    if (sig.signal === "BUY" || sig.signal === "SELL") {
      const res = simulateTrade(bars, i, sig);
      trades.push({ date: etDate(bars[i].t), dir: sig.signal, pts: res.pts, exit: res.exit });
      dayPnLUSD += res.pts * PV_MNQ;
      i = res.exitIdx + 1; // no overlapping positions
    } else {
      i++;
    }
  }
  return tally(trades);
}

function line(name, r) {
  return `${name.padEnd(26)} ${String(r.n).padStart(3)} tr  ${String(r.wins + "W/" + r.losses + "L").padStart(8)}  win ${fmt(r.winRate, 0).padStart(3)}%  PF ${(r.pf === Infinity ? "inf" : fmt(r.pf, 2)).padStart(5)}  net ${money(r.netUSD).padStart(8)}/MNQ`;
}

function buildEmbed(rows, meta) {
  const ranked = [...rows].sort((a, b) => b.r.netUSD - a.r.netUSD);
  const winner = ranked[0];
  return {
    content: "🧪 **Simple Strategy shootout** — the 3 best TradingView versions on ProjectX data",
    allowed_mentions: { parse: [] },
    embeds: [{
      title: `Simple Strategy v5 / v3 / v5-loose · ${meta.days}-day ProjectX replay`,
      description:
        `The original TradingView system (BB 12/2 + MACD 12/26/9 + RSI 7, ADX>20, EMA200 trend, ADR stop/target, breakeven at +1R), 1 MNQ. ` +
        `This window is the **choppy June regime** — ADR is approximated from only ~${meta.days} days of intraday history, so read it as a relative check, not the long-run edge.`,
      color: winner.r.netUSD >= 0 ? 0x2ecc71 : 0xe74c3c,
      fields: rows.map((row) => ({
        name: row.name,
        value: `${row.r.n} trades · ${row.r.wins}W/${row.r.losses}L · win ${fmt(row.r.winRate, 0)}% · PF ${row.r.pf === Infinity ? "∞" : fmt(row.r.pf, 2)} · **${money(row.r.netUSD)}/MNQ**`,
        inline: false,
      })).concat([{ name: "🏆 Best this regime", value: `**${winner.name}** (${money(winner.r.netUSD)}/MNQ)`, inline: false }]),
      footer: { text: "Backtest · ProjectX 5-min · 1 MNQ · data-only, no orders · TopStep-compliant" },
    }],
  };
}

(async () => {
  const doPost = process.argv.includes("--post");
  const bars = await getBars();
  const days = new Set(bars.map((b) => dayKeyOf(b.t))).size;
  console.log(`Comparing the 3 Simple Strategy versions over ${bars.length} bars / ${days} ET days (ProjectX), 1 MNQ.\n`);

  const rows = [
    { name: Simple.PRESETS.v5.label, r: runVersion(bars, Simple.PRESETS.v5) },
    { name: Simple.PRESETS.v3.label, r: runVersion(bars, Simple.PRESETS.v3) },
    { name: Simple.PRESETS.v5loose.label, r: runVersion(bars, Simple.PRESETS.v5loose) },
  ];

  for (const row of rows) console.log(line(row.name, row.r));
  console.log("");
  for (const row of rows) {
    if (!row.r.trades.length) continue;
    console.log(`${row.name}:`);
    for (const t of row.r.trades) {
      console.log(`  ${t.date} ${t.dir} -> ${t.exit} ${fmt(t.pts, 1)}pt`);
    }
  }

  if (doPost) {
    const payload = buildEmbed(rows, { days });
    const hook = getWebhook();
    if (!hook) throw new Error("no webhook — set DISCORD_WEBHOOK_URL or secrets.local.js");
    const r = await fetch(hook, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!r.ok) throw new Error("discord " + r.status + " " + (await r.text()));
    console.log("\nPosted Simple Strategy shootout to Discord.");
  }
})().catch((e) => { console.error("backtest-simple error:", e.message); process.exit(1); });
