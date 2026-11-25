// =============================================================
//  backtest-meanrev-stop.js — does a TIGHTER stop on mean-rev v1.1 cut our
//  losses, or does it just bleed the edge? Mean reversion fades a move that
//  is still extending, so a tight stop tends to get tagged right before the
//  snap-back — cutting the exact trades the edge lives on.
//
//  This harness does NOT modify meanrev.js. It overrides ONLY the stop on a
//  copied signal (entry, target=mean, dir, regime/trend filters, and the
//  symmetric long/short logic all stay identical to v1.1) and replays the
//  same ProjectX bars. Variants:
//    - baseline : stop = 1.0 x ATR(14)   (the locked v1.1)
//    - 0.75xATR : stop = 0.75 x ATR
//    - 0.50xATR : stop = 0.50 x ATR
//    - cap20pt  : stop = min(ATR stop, 20 pts)   (hard $ cap: $40/MNQ)
//    - cap12pt  : stop = min(ATR stop, 12 pts)   (hard $ cap: $24/MNQ)
//    - cap8pt   : stop = min(ATR stop,  8 pts)   (hard $ cap: $16/MNQ)
//  Adopt a tighter stop ONLY if net holds up AND win% / maxDD don't crater.
//
//  DATA-ONLY / TopStep-compliant: reads history, never places an order.
//  Run:  node backtest-meanrev-stop.js [--post]
//  Consumes bars = [{ t, o, h, l, c, v }], t = epoch SECONDS, ascending.
// =============================================================
"use strict";

require("./public/indicators.js");
require("./public/meanrev.js");
const MeanRev = globalThis.MeanRev;
const ProjectX = require("./projectx.js");

const PV_MNQ = 2, PV_NQ = 20;

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
  // --yahoo: free ~58-day 5m sample (NQ=F). Default: ProjectX sim history (~12 days).
  if (process.argv.includes("--yahoo")) {
    const Yahoo = require("./yahoo.js");
    const bars = await Yahoo.fetchBars({ interval: "5m", range: "60d" });
    if (!bars.length) throw new Error("Yahoo returned 0 bars");
    return bars;
  }
  const bars = await ProjectX.fetchBars({ unitNumber: 5, lookbackDays: 60 });
  if (!bars.length) throw new Error("ProjectX returned 0 bars");
  return bars;
}

// Variant definitions: how to derive the NEW stop distance (in points) from
// the original v1.1 stop distance (1.0 x ATR).
const VARIANTS = {
  baseline: (orig) => orig,
  "0.75xATR": (orig) => orig * 0.75,
  "0.50xATR": (orig) => orig * 0.5,
  cap20pt: (orig) => Math.min(orig, 20),
  cap12pt: (orig) => Math.min(orig, 12),
  cap8pt: (orig) => Math.min(orig, 8),
};

// Return a NEW signal with only the stop tightened. Target/entry/dir untouched.
function applyStop(sig, mode) {
  const f = VARIANTS[mode];
  if (!f || mode === "baseline") return sig;
  const newPts = f(sig.stopPts);
  const stop = sig.dir === 1 ? sig.entry - newPts : sig.entry + newPts;
  return { ...sig, stop, stopPts: newPts };
}

function simulateTrade(bars, entryIdx, sig) {
  const dayKey = dayKeyOf(bars[entryIdx].t);
  const isLong = sig.dir === 1;
  const entry = sig.entry;
  for (let k = entryIdx + 1; k < bars.length; k++) {
    if (dayKeyOf(bars[k].t) !== dayKey) break;
    const b = bars[k];
    const hitStop = isLong ? b.l <= sig.stop : b.h >= sig.stop;
    const hitTgt = isLong ? b.h >= sig.target : b.l <= sig.target;
    if (hitStop) return { pts: isLong ? sig.stop - entry : entry - sig.stop, exit: "stop", exitIdx: k };
    if (hitTgt) return { pts: isLong ? sig.target - entry : entry - sig.target, exit: "target", exitIdx: k };
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
  const worstPts = trades.reduce((m, t) => Math.min(m, t.pts), 0); // most negative single trade
  let peak = 0, cum = 0, maxDD = 0;
  for (const t of trades) { cum += t.pts; peak = Math.max(peak, cum); maxDD = Math.max(maxDD, peak - cum); }
  return {
    n: trades.length, wins: wins.length, losses: losses.length,
    winRate: trades.length ? (wins.length / trades.length) * 100 : 0,
    netPts, ddPts: maxDD, worstPts,
    netMNQ: netPts * PV_MNQ, netNQ: netPts * PV_NQ,
    worstMNQ: worstPts * PV_MNQ,
    pf: grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? Infinity : 0),
  };
}

function runVariant(bars, mode) {
  const trades = [];
  let maxStopPts = 0; // largest stop DISTANCE actually placed (tail-risk proxy)
  let i = 1;
  while (i < bars.length) {
    const raw = MeanRev.computeMeanRev(bars, i);
    if (raw.signal === "BUY" || raw.signal === "SELL") {
      const sig = applyStop(raw, mode);
      maxStopPts = Math.max(maxStopPts, sig.stopPts);
      const res = simulateTrade(bars, i, sig);
      trades.push({ date: etDate(bars[i].t), dir: raw.signal, pts: res.pts, exit: res.exit });
      i = res.exitIdx + 1;
    } else { i++; }
  }
  const t = tally(trades);
  t.trades = trades;
  t.maxStopPts = maxStopPts;
  return t;
}

// Scale a variant's result to N MNQ and report the things that decide Combine
// survival: worst single trade, worst DAY, tail-risk (max stop placed), and
// estimated trading days to the $3,000 target.
function focus5MNQ(name, r, contracts) {
  const PV = PV_MNQ * contracts;
  const byDay = new Map();
  for (const tr of r.trades) byDay.set(tr.date, (byDay.get(tr.date) || 0) + tr.pts);
  const worstDayPts = Math.min(0, ...byDay.values());
  const net = r.netPts * PV;
  const dailyDays = new Set(r.trades.map((t) => t.date)).size || 1;
  const perDay = net / dailyDays;
  const daysToTarget = perDay > 0 ? Math.ceil(3000 / perDay) : Infinity;
  console.log(`\n=== ${name} @ ${contracts} MNQ ($${PV}/pt) ===`);
  console.log(`  net over sample      : ${money(net)} (${dailyDays} trading days)`);
  console.log(`  worst single trade   : ${money(r.worstPts * PV)}`);
  console.log(`  worst day            : ${money(worstDayPts * PV)}`);
  console.log(`  biggest stop placed  : ${fmt(r.maxStopPts, 1)}pt = ${money(r.maxStopPts * PV)}  <- NOT hard-capped (½×ATR floats with volatility)`);
  console.log(`  est. days to $3,000  : ~${daysToTarget} trading days`);
  console.log(`  daily-loss limit $1,000 : ${(-worstDayPts * PV) < 1000 ? "OK (worst day inside)" : "BREACH risk"}`);
  console.log(`  trailing MLL $2,000     : worst day uses ${fmt(((-worstDayPts * PV) / 2000) * 100, 0)}% of the buffer`);
}

function line(name, r) {
  return `${name.padEnd(12)} ${String(r.n).padStart(2)} tr  ${(r.wins + "W/" + r.losses + "L").padStart(7)}  win ${fmt(r.winRate, 0).padStart(3)}%  PF ${(r.pf === Infinity ? "inf" : fmt(r.pf, 2)).padStart(5)}  MNQ ${money(r.netMNQ).padStart(7)}  NQ ${money(r.netNQ).padStart(8)}  worst-trade ${money(r.worstMNQ).padStart(6)}/MNQ  maxDD ${fmt(r.ddPts, 0)}pt`;
}

(async () => {
  const doPost = process.argv.includes("--post");
  const bars = await getBars();
  const days = new Set(bars.map((b) => dayKeyOf(b.t))).size;
  console.log(`Mean-rev v1.1 STOP-tightening over ${bars.length} bars / ${days} ET days (ProjectX). Entry+target unchanged.\n`);

  const modes = Object.keys(VARIANTS);
  const rows = modes.map((m) => ({ name: m, r: runVariant(bars, m) }));
  for (const row of rows) console.log(line(row.name, row.r));

  // Focus: half stop vs 12pt hard cap, both at 5 MNQ (apples-to-apples).
  const half = rows.find((row) => row.name === "0.50xATR");
  if (half) focus5MNQ("0.50xATR (half stop)", half.r, 5);
  const cap = rows.find((row) => row.name === "cap12pt");
  if (cap) focus5MNQ("cap12pt (hard cap)", cap.r, 5);

  if (doPost) {
    const base = rows[0].r;
    const payload = {
      content: "🛑 **Mean-rev v1.1 — tighter-stop test** (entry & target unchanged, ProjectX)",
      allowed_mentions: { parse: [] },
      embeds: [{
        title: `Can a tighter stop cut losses without killing the edge? · ${days}-day replay`,
        description: `Same entry, same target (the mean), only the STOP is tightened. Mean-rev fades extending moves, so tight stops often get tagged before the snap-back. Adopt only if net holds AND win%/maxDD don't crater. (Small choppy sample — directional, not a verdict.)`,
        color: 0x3498db,
        fields: rows.map((row) => ({
          name: row.name + (row.name === "baseline" ? " (v1.1)" : ""),
          value: `${row.r.n} tr · win ${fmt(row.r.winRate, 0)}% · PF ${row.r.pf === Infinity ? "∞" : fmt(row.r.pf, 2)} · MNQ **${money(row.r.netMNQ)}** · worst trade ${money(row.r.worstMNQ)}/MNQ · maxDD ${fmt(row.r.ddPts, 0)}pt`,
          inline: false,
        })),
        footer: { text: "Backtest · ProjectX 5-min · 1 MNQ · data-only, no orders · TopStep-compliant" },
      }],
    };
    const hook = getWebhook();
    if (!hook) throw new Error("no webhook — set DISCORD_WEBHOOK_URL or secrets.local.js");
    const r = await fetch(hook, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!r.ok) throw new Error("discord " + r.status + " " + (await r.text()));
    console.log("\nPosted stop-tightening card to Discord.");
  }
})().catch((e) => { console.error("stop-test error:", e.message); process.exit(1); });
