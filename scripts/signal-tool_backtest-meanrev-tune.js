// =============================================================
//  backtest-meanrev-tune.js — can we squeeze MORE profit out of mean-rev
//  v1.1 (especially on LONGS) WITHOUT changing the entry edge or the risk?
//
//  The locked v1.1 exits longs at the BB basis (the mean), which is often
//  close to entry -> small wins. This harness keeps the entry, the stop, and
//  the regime/trend filters 100% identical (it does NOT modify meanrev.js);
//  it only swaps the LONG target and replays the same ProjectX bars:
//    - baseline   : long target = BB basis (the locked v1.1 exit)
//    - upperBand  : long target = the opposite (upper) band — full traverse
//    - 2R         : long target = entry + 2 x stop distance
//    - 1.5R       : long target = entry + 1.5 x stop distance
//  SHORTS are left exactly as v1.1 in every variant, so the only change
//  under test is "let longs run". Adopt a variant ONLY if it lifts net
//  without hurting win rate or drawdown.
//
//  DATA-ONLY / TopStep-compliant: reads history, never places an order.
//  Run:  node backtest-meanrev-tune.js [--post]
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
  const bars = await ProjectX.fetchBars({ unitNumber: 5, lookbackDays: 60 });
  if (!bars.length) throw new Error("ProjectX returned 0 bars");
  return bars;
}

// Return a NEW signal with the LONG target swapped per `mode`. Shorts and
// everything else (entry, stop, dir) are passed through untouched.
function applyVariant(sig, mode) {
  if (sig.dir !== 1 || mode === "baseline") return sig; // shorts + baseline: as-is
  const entry = sig.entry;
  const stopPts = sig.stopPts; // entry - stop for a long
  let target = sig.target;
  if (mode === "upperBand" && sig.upperBB != null) target = sig.upperBB;
  else if (mode === "2R") target = entry + 2 * stopPts;
  else if (mode === "1.5R") target = entry + 1.5 * stopPts;
  // never let the "extended" target be worse than the mean target
  target = Math.max(target, sig.target);
  return { ...sig, target, tgtPts: target - entry };
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
  const longs = trades.filter((t) => t.dir === "BUY");
  const wins = trades.filter((t) => t.pts > 0);
  const grossWin = wins.reduce((s, t) => s + t.pts, 0);
  const grossLoss = Math.abs(trades.filter((t) => t.pts <= 0).reduce((s, t) => s + t.pts, 0));
  const netPts = trades.reduce((s, t) => s + t.pts, 0);
  const longPts = longs.reduce((s, t) => s + t.pts, 0);
  let peak = 0, cum = 0, maxDD = 0;
  for (const t of trades) { cum += t.pts; peak = Math.max(peak, cum); maxDD = Math.max(maxDD, peak - cum); }
  return {
    n: trades.length, wins: wins.length, losses: trades.length - wins.length,
    winRate: trades.length ? (wins.length / trades.length) * 100 : 0,
    netPts, longPts, ddPts: maxDD,
    netMNQ: netPts * PV_MNQ, netNQ: netPts * PV_NQ,
    longMNQ: longPts * PV_MNQ,
    pf: grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? Infinity : 0),
  };
}

function runVariant(bars, mode) {
  const trades = [];
  let i = 1;
  while (i < bars.length) {
    const raw = MeanRev.computeMeanRev(bars, i);
    if (raw.signal === "BUY" || raw.signal === "SELL") {
      const sig = applyVariant(raw, mode);
      const res = simulateTrade(bars, i, sig);
      trades.push({ date: etDate(bars[i].t), dir: raw.signal, pts: res.pts, exit: res.exit });
      i = res.exitIdx + 1;
    } else { i++; }
  }
  return tally(trades);
}

function line(name, r) {
  return `${name.padEnd(20)} ${String(r.n).padStart(2)} tr  ${(r.wins + "W/" + r.losses + "L").padStart(7)}  win ${fmt(r.winRate, 0).padStart(3)}%  PF ${(r.pf === Infinity ? "inf" : fmt(r.pf, 2)).padStart(5)}  MNQ ${money(r.netMNQ).padStart(7)}  NQ ${money(r.netNQ).padStart(8)}  longs ${money(r.longMNQ).padStart(7)}/MNQ  maxDD ${fmt(r.ddPts, 0)}pt`;
}

(async () => {
  const doPost = process.argv.includes("--post");
  const bars = await getBars();
  const days = new Set(bars.map((b) => dayKeyOf(b.t))).size;
  console.log(`Mean-rev v1.1 LONG-target tuning over ${bars.length} bars / ${days} ET days (ProjectX). Entry+stop unchanged.\n`);

  const modes = ["baseline", "1.5R", "2R", "upperBand"];
  const rows = modes.map((m) => ({ name: m === "baseline" ? "baseline (mean)" : "longs -> " + m, r: runVariant(bars, m) }));
  for (const row of rows) console.log(line(row.name, row.r));

  if (doPost) {
    const base = rows[0].r;
    const ranked = [...rows].sort((a, b) => b.r.netMNQ - a.r.netMNQ);
    const win = ranked[0];
    const payload = {
      content: "🔧 **Mean-rev v1.1 — long-target tuning** (entry & stop unchanged, ProjectX)",
      allowed_mentions: { parse: [] },
      embeds: [{
        title: `Can we let LONGS run? · ${days}-day ProjectX replay`,
        description: `Same entry, same stop, only the LONG exit target changes. Shorts identical to v1.1. Adopt only if net rises without hurting win% or drawdown. (Small choppy sample — directional, not a verdict.)`,
        color: win.r.netMNQ >= base.netMNQ ? 0x2ecc71 : 0xe67e22,
        fields: rows.map((row) => ({
          name: row.name,
          value: `${row.r.n} tr · win ${fmt(row.r.winRate, 0)}% · PF ${row.r.pf === Infinity ? "∞" : fmt(row.r.pf, 2)} · MNQ **${money(row.r.netMNQ)}** · longs ${money(row.r.longMNQ)} · maxDD ${fmt(row.r.ddPts, 0)}pt`,
          inline: false,
        })),
        footer: { text: "Backtest · ProjectX 5-min · 1 MNQ · data-only, no orders · TopStep-compliant" },
      }],
    };
    const hook = getWebhook();
    if (!hook) throw new Error("no webhook — set DISCORD_WEBHOOK_URL or secrets.local.js");
    const r = await fetch(hook, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!r.ok) throw new Error("discord " + r.status + " " + (await r.text()));
    console.log("\nPosted long-tuning card to Discord.");
  }
})().catch((e) => { console.error("tune error:", e.message); process.exit(1); });
