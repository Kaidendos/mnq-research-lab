// =============================================================
//  lunch-paper.js — DRY-RUN paper-trader for the LUNCH strategy candidate.
//
//  Strategy: Keltner Band Fade (lab-new4 `keltFade` trigger, reused verbatim)
//  with an ENGINEERED bracket — stop 0.7xATR / target 2.5xATR, 1 trade/day —
//  in the LUNCH window (12:00-13:30 ET entry, flat by 16:00 ET).
//
//  *** PAPER ONLY. This file imports NO order module and has NO order code. ***
//  It tracks a VIRTUAL position and posts "WOULD ENTER / WOULD EXIT" to Discord
//  so we can forward-test it on fresh out-of-sample data alongside the LIVE
//  champion (live-signal.js) — which this does not touch in any way.
//
//  Separate state files from the champion (.lunch-* vs .live-*) so the two
//  processes never collide. Run:  node lunch-paper.js  (or --once for a snapshot)
// =============================================================
"use strict";

require("./public/indicators.js");
const fs = require("fs");
const path = require("path");
const Lab = require("./lab-new4.js");
const PX = require("./projectx.js");
const Notify = require("./notify.js");
const { renderTradeChart } = require("./chart.js");
const I = globalThis.Indicators;

// ---- strategy config (the engineered lunch candidate from journal (xx)) ----
const STRAT_KEY = "keltFade";              // lab-new4 signal to reuse
const STRAT_NAME = "Keltner Band Fade (lunch)";
const STOP_MULT = 0.7, TGT_MULT = 2.5;     // ATR multiples (engineered bracket)
const LUNCH_START = 720, LUNCH_END = 810;  // 12:00-13:30 ET (entry window)
const RTH_END = 960;                        // 16:00 ET — flat by close
const MAX_TRADES_DAY = 1;
const CONTRACTS = 5, PV = 2;                // 5 MNQ, $2/pt  -> $10/pt
const POLL_MS = 60_000;
const MAX_BAR_AGE = 600;                    // stale-feed guard (seconds): 5-min bars are open-stamped,
                                            // so a fresh bar is ~300s+delay old; 600s allows it, rejects a frozen feed
const CHART_LOOKBACK = 70;

// ---- separate file set (never collides with the live champion) ----
const LOG = path.join(__dirname, "logs", "lunch-signals.jsonl");
const STATE_FILE = path.join(__dirname, ".lunch-state.json");
const HEARTBEAT_FILE = path.join(__dirname, ".lunch-heartbeat");
const LOCK = path.join(__dirname, ".lunch-lock");
const CHART_DIR = path.join(__dirname, "logs", "lunch-charts");

const DISCORD_GREEN = 0x2ecc71, DISCORD_RED = 0xe74c3c, DISCORD_BLUE = 0x3498db, GOLD = 0xf1c40f;
const f = (x, d = 2) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));
const money = (x) => (x >= 0 ? "+$" : "-$") + f(Math.abs(x), 0);

function audit(rec) {
  try { fs.mkdirSync(path.dirname(LOG), { recursive: true }); fs.appendFileSync(LOG, JSON.stringify({ ts: new Date().toISOString(), ...rec }) + "\n"); } catch {}
}
function etParts(t) { return Lab.etParts(t); }
function loadState() { try { return JSON.parse(fs.readFileSync(STATE_FILE, "utf8")); } catch { return {}; } }
function saveState(s) { try { fs.writeFileSync(STATE_FILE, JSON.stringify(s)); } catch {} }
let openPos = loadState().openPos || null;
let day = { key: null, trades: 0 };
function rollDay(k) { if (day.key !== k) day = { key: k, trades: 0 }; }

function writeHeartbeat(extra = {}) {
  try {
    fs.writeFileSync(HEARTBEAT_FILE, JSON.stringify({
      ts: new Date().toISOString(), pid: process.pid, mode: "PAPER", strategy: STRAT_KEY,
      openPos: !!openPos, dayTrades: day.trades, ...extra,
    }));
  } catch {}
}

// ---- signal: reuse lab keltFade trigger verbatim, override bracket to ATR x mults ----
function lunchSignalAt(bars) {
  const last = bars.length - 1;
  const high = bars.map((b) => b.h), low = bars.map((b) => b.l), close = bars.map((b) => b.c);
  const atr = I.atr(high, low, close, 14);
  const raw = Lab.buildAll(bars)[STRAT_KEY][last];
  const a = atr[last];
  if (!raw || a == null) return { last, sig: null, atr: a };
  const mins = etParts(bars[last].t).mins;
  if (mins < LUNCH_START || mins > LUNCH_END) return { last, sig: null, atr: a };
  const dir = raw.dir, entry = raw.entry;
  const sig = { dir, entry, stop: entry - dir * STOP_MULT * a, target: entry + dir * TGT_MULT * a };
  return { last, sig, atr: a };
}

function notifyTrade(kind, bars, info) {
  try {
    const png = renderTradeChart(bars, {
      lookback: CHART_LOOKBACK, dir: info.dir, entry: info.entry, stop: info.stop,
      target: info.target, entryT: info.entryT, exit: info.exit, exitT: info.exitT,
    });
    try { fs.mkdirSync(CHART_DIR, { recursive: true }); fs.writeFileSync(path.join(CHART_DIR, `${info.barT}-${kind}.png`), png); } catch {}
    const side = info.dir === 1 ? "LONG" : "SHORT";
    const isEntry = kind === "ENTRY";
    const color = isEntry ? DISCORD_BLUE : (info.pnl >= 0 ? DISCORD_GREEN : DISCORD_RED);
    const fields = isEntry
      ? [
          { name: "Side", value: side, inline: true },
          { name: "Size", value: `${CONTRACTS} MNQ (paper)`, inline: true },
          { name: "Entry", value: f(info.entry), inline: true },
          { name: "Stop", value: `${f(info.stop)} (${STOP_MULT}×ATR)`, inline: true },
          { name: "Target", value: `${f(info.target)} (${TGT_MULT}×ATR)`, inline: true },
          { name: "Risk / Reward", value: `${money(-info.risk)} / ${money(info.reward)}`, inline: true },
        ]
      : [
          { name: "Exit reason", value: String(info.why), inline: true },
          { name: "Exit", value: f(info.exit), inline: true },
          { name: "Points", value: f(info.pts), inline: true },
          { name: "Paper P&L", value: money(info.pnl), inline: true },
          { name: "Side", value: side, inline: true },
          { name: "Size", value: `${CONTRACTS} MNQ (paper)`, inline: true },
        ];
    const title = isEntry
      ? `🥗📝 LUNCH PAPER — WOULD ENTER ${side} (${STRAT_NAME})`
      : `🥗📝 LUNCH PAPER — WOULD EXIT (${info.why}) ${money(info.pnl)}`;
    const payload = {
      embeds: [{
        title,
        description: "📝 **PAPER TRADE — SIMULATED, NO REAL ORDER PLACED.** Forward-test of the lunch Keltner-fade candidate. The live champion is unaffected.",
        color, fields,
        image: { url: "attachment://chart.png" },
        footer: { text: `📝 PAPER / DRY-RUN · ${CONTRACTS} MNQ simulated · ${STRAT_KEY} · ${new Date(info.barT * 1000).toISOString()}` },
      }],
    };
    Notify.postImage(payload, png, "chart.png").catch(() => {});
  } catch (e) { console.error("[lunch] chart/post failed:", e.message); }
}

function processLatest(bars) {
  const b = bars[bars.length - 1];
  const c = etParts(b.t);
  rollDay(c.k);
  const stamp = new Date(b.t * 1000).toISOString();

  // stale-feed guard: don't act on old data
  const ageSec = Math.round(Date.now() / 1000 - b.t);

  // ---- manage an open virtual position ----
  if (openPos) {
    const isLong = openPos.dir === 1;
    let exit = null;
    // flat at RTH end or on a new day
    if (c.mins >= RTH_END || c.k !== openPos.entryDay) exit = { px: b.c, why: "eod-flat" };
    else if (isLong ? b.l <= openPos.stop : b.h >= openPos.stop) exit = { px: openPos.stop, why: "stop" };
    else if (isLong ? b.h >= openPos.target : b.l <= openPos.target) exit = { px: openPos.target, why: "target" };
    if (exit) {
      const pts = isLong ? exit.px - openPos.entry : openPos.entry - exit.px;
      const pnl = pts * CONTRACTS * PV;
      console.log(`[${stamp}] WOULD EXIT (${exit.why}) @ ${f(exit.px)}  pts ${f(pts)}  ${money(pnl)}  *** PAPER ***`);
      audit({ kind: "INTENT_EXIT", dir: openPos.dir, entry: openPos.entry, exit: exit.px, why: exit.why, pts, pnl, barT: b.t });
      notifyTrade("EXIT", bars, { dir: openPos.dir, entry: openPos.entry, stop: openPos.stop, target: openPos.target, entryT: openPos.entryT, exit: exit.px, exitT: b.t, why: exit.why, pts, pnl, barT: b.t });
      openPos = null; saveState({ openPos: null });
    }
    return;
  }

  // ---- look for a new entry (lunch window, under daily cap, fresh feed) ----
  if (day.trades >= MAX_TRADES_DAY) return;
  if (ageSec > MAX_BAR_AGE) return;                 // stale feed — skip
  const { sig } = lunchSignalAt(bars);
  if (!sig) return;
  const side = sig.dir === 1 ? "LONG" : "SHORT";
  const risk = Math.abs(sig.entry - sig.stop) * CONTRACTS * PV;
  const reward = Math.abs(sig.target - sig.entry) * CONTRACTS * PV;
  openPos = { dir: sig.dir, entry: sig.entry, stop: sig.stop, target: sig.target, entryDay: c.k, entryT: b.t };
  day.trades++;
  saveState({ openPos });
  console.log(`[${stamp}] WOULD ENTER ${side} @ ${f(sig.entry)}  stop ${f(sig.stop)}  target ${f(sig.target)}  ${CONTRACTS} MNQ  *** PAPER ***`);
  audit({ kind: "INTENT_ENTRY", dir: side, entry: sig.entry, stop: sig.stop, target: sig.target, size: CONTRACTS, risk, barT: b.t });
  notifyTrade("ENTRY", bars, { dir: sig.dir, entry: sig.entry, stop: sig.stop, target: sig.target, risk, reward, entryT: b.t, barT: b.t });
}

async function getBars() {
  const bars = await PX.fetchBars({ unitNumber: 5, lookbackDays: 5, contract: "MNQ", live: false });
  return bars.filter((b) => b && isFinite(b.c)).sort((a, b) => a.t - b.t);
}

(async function main() {
  const once = process.argv.includes("--once");
  console.log(`LUNCH PAPER-TRADER (DRY-RUN, NO ORDERS) — ${STRAT_NAME}`);
  console.log(`Strategy ${STRAT_KEY} · bracket ${STOP_MULT}/${TGT_MULT}×ATR · ${MAX_TRADES_DAY}/day · window 12:00-13:30 ET · ${CONTRACTS} MNQ paper`);
  console.log(`Audit -> ${LOG}\n`);

  let bars = await getBars();
  if (!bars.length) { console.error("No bars from feed."); process.exit(1); }
  const lastClosed = bars[bars.length - 1];
  console.log(`Loaded ${bars.length} bars; latest closed ${new Date(lastClosed.t * 1000).toISOString()} (ET min ${etParts(lastClosed.t).mins}).`);

  // --demo: fabricate a sample paper entry + exit and post BOTH to Discord, to
  // confirm the "PAPER TRADE" labeling renders correctly. Touches no state.
  if (process.argv.includes("--demo")) {
    const e = bars[Math.max(0, bars.length - 6)], x = bars[bars.length - 1];
    const dir = 1, entry = e.c, atrGuess = Math.max(5, (e.h - e.l) || 10);
    const stop = entry - STOP_MULT * atrGuess, target = entry + TGT_MULT * atrGuess;
    const pts = x.c - entry, pnl = pts * CONTRACTS * PV;
    console.log("[--demo] posting sample PAPER entry + exit to Discord...");
    notifyTrade("ENTRY", bars, { dir, entry, stop, target, risk: Math.abs(entry - stop) * CONTRACTS * PV, reward: Math.abs(target - entry) * CONTRACTS * PV, entryT: e.t, barT: e.t });
    notifyTrade("EXIT", bars, { dir, entry, stop, target, entryT: e.t, exit: x.c, exitT: x.t, why: "demo", pts, pnl, barT: x.t });
    await new Promise((r) => setTimeout(r, 4000));
    console.log("[--demo] done — check Discord for two 🥗📝 PAPER cards.");
    return;
  }

  await processLatest(bars);
  const nowMins = etParts(lastClosed.t).mins;
  if (!openPos && (nowMins < LUNCH_START || nowMins > LUNCH_END)) {
    console.log(`(Outside the 12:00-13:30 ET lunch window — no entry expected until then. ET min ${nowMins}.)`);
  }
  if (once) { console.log("\n--once: evaluated latest bars, exiting."); return; }

  // single-instance lock (separate from champion's .live-lock)
  try {
    const prev = parseInt(fs.readFileSync(LOCK, "utf8"), 10);
    if (prev && prev !== process.pid) { try { process.kill(prev, 0); console.log(`Another lunch-paper instance (pid ${prev}) running — exiting.`); return; } catch {} }
  } catch {}
  fs.writeFileSync(LOCK, String(process.pid));
  const releaseLock = () => { try { if (parseInt(fs.readFileSync(LOCK, "utf8"), 10) === process.pid) fs.unlinkSync(LOCK); } catch {} };
  process.on("exit", releaseLock);
  process.on("SIGINT", () => { releaseLock(); process.exit(0); });

  let lastT = lastClosed.t;
  writeHeartbeat({ event: "startup" });
  console.log(`\nLunch paper loop started — polling every ${POLL_MS / 1000}s. Ctrl+C to stop.`);
  Notify.postJSON({
    embeds: [{
      title: "🥗📝 Lunch paper-trader ONLINE (DRY-RUN)",
      color: GOLD,
      description: `Forward-testing **${STRAT_NAME}** — ${STOP_MULT}/${TGT_MULT}×ATR, ${MAX_TRADES_DAY} trade/day, 12:00–13:30 ET, ${CONTRACTS} MNQ **paper (no real orders)**.\nPosts a would-be entry & exit chart per trade. The live champion is unaffected.`,
      footer: { text: `online ${new Date().toISOString()}` },
    }],
  }).catch(() => {});

  setInterval(async () => {
    try {
      const fresh = await getBars();
      const latest = fresh[fresh.length - 1];
      const lastBarT = latest ? latest.t : null;
      if (latest && latest.t > lastT) { lastT = latest.t; await processLatest(fresh); }
      writeHeartbeat({ lastBarT, lastBarAgeSec: lastBarT ? Math.round(Date.now() / 1000 - lastBarT) : null });
    } catch (e) { console.error(`[lunch poll error] ${e.message}`); writeHeartbeat({ pollError: String(e.message).slice(0, 120) }); }
  }, POLL_MS);
})().catch((e) => { console.error("[lunch FATAL]", e); process.exit(1); });
