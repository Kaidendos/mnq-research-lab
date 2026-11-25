// =============================================================
//  live-fvg.js — PAPER (dry-run) forward-test of the optimized FVG strategy.
//
//  Strategy (from optimize-strat.js, stress-tested net of fees/slippage):
//    Entry  : FVG retest (win6, gap≥0.2·ATR) + ADX(14)>20 filter, any RTH bar.
//    Exit   : stop 1.5·ATR / target 3.5·ATR bracket, flat by 16:00 ET.
//    Size   : vol-based, $200 risk cap, ≤5 MNQ.
//    Brakes : max 3 trades/day, daily-loss stop -$500, one position at a time.
//
//  PAPER ONLY — places NO orders (forward test on the practice account's data).
//  Reuses the data feed, Discord notifier and chart renderer from the live bot.
//  Run:  node live-fvg.js            (paper live loop)
//        node live-fvg.js --once     (evaluate latest bar once, exit)
// =============================================================
"use strict";
const fs = require("fs");
const path = require("path");
const Lab = require("./lab-new4.js");
const G = require("./strat-gen.js");
const O = require("./optimize-strat.js");
const PX = require("./projectx.js");
const Notify = require("./notify.js");
const { renderTradeChart } = require("./chart.js");

// ---- strategy params (the optimized winner) ----
const PV = 2, MAXC = 5, RISK_CAP = 200, STOP_MULT = 1.5, TGT_MULT = 3.5;
const MAX_TRADES_DAY = 3, DAY_STOP = -500;
const baseFn = G.ENTRIES.find(e => e[0] === "fvg_w6_g02")[3];
const dirFn = O.withFilter(baseFn, "adx");   // FVG retest + ADX>20

const POLL_MS = 60_000, RTH_END = 960, CHART_LOOKBACK = 70, MAX_BAR_AGE = 600;
const LOG = path.join(__dirname, "logs", "fvg-paper-signals.jsonl");
const STATE_FILE = path.join(__dirname, ".fvg-paper-state.json");
const HEARTBEAT = path.join(__dirname, ".fvg-paper-heartbeat");
const LOCK = path.join(__dirname, ".fvg-paper-lock");
const CHART_DIR = path.join(__dirname, "logs", "fvg-charts");
const DISCORD_GREEN = 0x2ecc71, DISCORD_RED = 0xe74c3c, DISCORD_BLUE = 0x2980b9;

const f = (x, d = 2) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));
const money = x => (x >= 0 ? "+$" : "-$") + f(Math.abs(x), 0);
const ep = Lab.etParts;
const inRTH = t => { const e = ep(t); return e.day !== 0 && e.day !== 6 && e.mins >= 570 && e.mins < RTH_END; };
function audit(rec) { fs.mkdirSync(path.dirname(LOG), { recursive: true }); fs.appendFileSync(LOG, JSON.stringify({ ts: new Date().toISOString(), ...rec }) + "\n"); }
function sizeFor(stopPts) { return Math.max(1, Math.min(MAXC, Math.floor(RISK_CAP / Math.max(1, stopPts * PV)))); }

let day = { key: null, realized: 0, trades: 0 };
function rollDay(k) { if (day.key !== k) day = { key: k, realized: 0, trades: 0 }; }
function loadState() { try { return JSON.parse(fs.readFileSync(STATE_FILE, "utf8")); } catch { return {}; } }
function saveState(s) { try { fs.writeFileSync(STATE_FILE, JSON.stringify(s)); } catch {} }
let openPos = loadState().openPos || null;
if (loadState().day) day = loadState().day;
function persist() { saveState({ openPos, day }); }
function heartbeat(extra = {}) { try { fs.writeFileSync(HEARTBEAT, JSON.stringify({ ts: new Date().toISOString(), pid: process.pid, openPos: !!openPos, dayRealized: day.realized, dayTrades: day.trades, ...extra })); } catch {} }

function notifyTrade(kind, bars, info) {
  try {
    const png = renderTradeChart(bars, { lookback: CHART_LOOKBACK, dir: info.dir, entry: info.entry, stop: info.stop, target: info.target, entryT: info.entryT, exit: info.exit, exitT: info.exitT });
    try { fs.mkdirSync(CHART_DIR, { recursive: true }); fs.writeFileSync(path.join(CHART_DIR, `${info.barT}-${kind}.png`), png); } catch {}
    const side = info.dir === 1 ? "LONG" : "SHORT", isEntry = kind === "ENTRY";
    const color = isEntry ? (info.dir === 1 ? DISCORD_GREEN : DISCORD_RED) : (info.pnl >= 0 ? DISCORD_GREEN : DISCORD_RED);
    const fields = isEntry
      ? [{ name: "Side", value: side, inline: true }, { name: "Size", value: `${info.size} MNQ`, inline: true }, { name: "Entry", value: f(info.entry), inline: true },
         { name: "Stop", value: f(info.stop), inline: true }, { name: "Target", value: f(info.target), inline: true }, { name: "Risk/Reward", value: `${money(-info.risk)} / ${money(info.reward)}`, inline: true }]
      : [{ name: "Exit", value: String(info.why), inline: true }, { name: "Price", value: f(info.exit), inline: true }, { name: "Points", value: f(info.pts), inline: true },
         { name: "P&L", value: money(info.pnl), inline: true }, { name: "Side", value: side, inline: true }, { name: "Size", value: `${info.size} MNQ`, inline: true }];
    const title = isEntry ? `🧪 PAPER — WOULD ENTER ${side} (FVG+ADX)` : `🧪 PAPER — WOULD EXIT (${info.why}) ${money(info.pnl)}`;
    Notify.postImage({ embeds: [{ title, color, fields, image: { url: "attachment://chart.png" }, footer: { text: `PAPER · FVG retest+ADX · ${new Date(info.barT * 1000).toISOString()}` } }] }, png, "chart.png").catch(() => {});
  } catch (e) { console.error("[notify] chart build failed:", e.message); }
}

async function processLatest(bars) {
  const i = bars.length - 1, b = bars[i], e = ep(b.t), stamp = new Date(b.t * 1000).toISOString();
  rollDay(e.k);
  let enteredThisBar = false;
  const dayStopped = day.realized <= DAY_STOP || day.trades >= MAX_TRADES_DAY;

  if (!openPos && !dayStopped && inRTH(b.t) && bars.length > 220) {
    const C = G.buildContext(bars);
    let d = 0; try { d = dirFn(C, i) || 0; } catch {}
    const a = C.atr[i];
    if (d && a != null) {
      const stopPts = STOP_MULT * a, tgtPts = TGT_MULT * a, size = sizeFor(stopPts), entry = b.c;
      const stop = d === 1 ? entry - stopPts : entry + stopPts, target = d === 1 ? entry + tgtPts : entry - tgtPts;
      const risk$ = stopPts * size * PV, reward$ = tgtPts * size * PV, side = d === 1 ? "LONG" : "SHORT";
      openPos = { dir: d, entry, stop, target, size, entryDay: e.k, entryT: b.t };
      enteredThisBar = true; day.trades++;
      console.log(`[${stamp}] PAPER WOULD ENTER ${side} @ ${f(entry)} stop ${f(stop)} tgt ${f(target)} ${size} MNQ risk ${money(-risk$)}`);
      audit({ kind: "PAPER_ENTRY", dir: side, entry, stop, target, size, risk: risk$, barT: b.t });
      persist();
      notifyTrade("ENTRY", bars, { dir: d, entry, stop, target, risk: risk$, reward: reward$, size, entryT: b.t, barT: b.t });
    }
  }

  if (openPos && !enteredThisBar) {
    const isLong = openPos.dir === 1, eod = (e.k !== openPos.entryDay || !inRTH(b.t));
    let exit = null;
    if (eod) exit = { px: bars[i - 1].c, why: "EOD" };
    else if (isLong ? b.l <= openPos.stop : b.h >= openPos.stop) exit = { px: openPos.stop, why: "stop" };
    else if (isLong ? b.h >= openPos.target : b.l <= openPos.target) exit = { px: openPos.target, why: "target" };
    if (exit) {
      const pts = isLong ? exit.px - openPos.entry : openPos.entry - exit.px, pnl = pts * openPos.size * PV;
      day.realized += pnl;
      console.log(`[${stamp}] PAPER WOULD EXIT (${exit.why}) @ ${f(exit.px)} ${f(pts)} pts ${money(pnl)} dayP&L ${money(day.realized)}`);
      audit({ kind: "PAPER_EXIT", why: exit.why, exit: exit.px, pts, pnl, size: openPos.size, dayRealized: day.realized, barT: b.t });
      notifyTrade("EXIT", bars, { dir: openPos.dir, entry: openPos.entry, stop: openPos.stop, target: openPos.target, size: openPos.size, entryT: openPos.entryT, exit: exit.px, exitT: b.t, why: exit.why, pts, pnl, barT: b.t });
      openPos = null; persist();
    }
  }
}

async function getBars() {
  const bars = await PX.fetchBars({ unitNumber: 5, lookbackDays: 5, contract: "MNQ", live: false });
  return bars.filter(b => b && isFinite(b.c)).sort((a, b) => a.t - b.t);
}

(async function main() {
  const once = process.argv.includes("--once");
  console.log("PAPER FVG forward-test — FVG retest + ADX>20 · s1.5/t3.5 · $200 cap · 3/day · -$500 dayStop · NO ORDERS");
  let bars = await getBars();
  if (!bars.length) { console.error("No bars from feed."); process.exit(1); }
  const last = bars[bars.length - 1];
  console.log(`Loaded ${bars.length} bars; latest closed ${new Date(last.t * 1000).toISOString()} (ET min ${ep(last.t).mins}).`);
  await processLatest(bars);
  if (once) { console.log("--once done."); return; }

  try { const prev = parseInt(fs.readFileSync(LOCK, "utf8"), 10); if (prev && prev !== process.pid) { try { process.kill(prev, 0); console.log(`Another paper instance (pid ${prev}) running — exiting.`); return; } catch {} } } catch {}
  fs.writeFileSync(LOCK, String(process.pid));
  const release = () => { try { if (parseInt(fs.readFileSync(LOCK, "utf8"), 10) === process.pid) fs.unlinkSync(LOCK); } catch {} };
  process.on("exit", release); process.on("SIGINT", () => { release(); process.exit(0); });

  let lastT = last.t;
  heartbeat({ event: "startup" });
  console.log(`\nPaper loop started — polling every ${POLL_MS / 1000}s. Ctrl+C to stop.`);
  Notify.postJSON({ embeds: [{ title: "🧪 PAPER bot ONLINE — FVG retest + ADX", color: DISCORD_BLUE, description: "Forward-testing the optimized **FVG retest + ADX>20** strategy on practice data — **paper only, no orders**.\nstop 1.5·ATR / target 3.5·ATR · $200 risk cap · ≤5 MNQ · max 3 trades/day · −$500 daily stop. Charts on every paper entry/exit.", footer: { text: `online ${new Date().toISOString()}` } }] }).catch(() => {});
  setInterval(async () => {
    try {
      const fresh = await getBars(); const latest = fresh[fresh.length - 1];
      if (latest && latest.t > lastT) {
        const age = Date.now() / 1000 - latest.t;
        if (age <= MAX_BAR_AGE) { lastT = latest.t; await processLatest(fresh); }
        else console.error(`[stale] latest bar ${Math.round(age)}s old — skipping.`);
      }
      heartbeat({ lastBarT: latest ? latest.t : null });
    } catch (e) { console.error(`[poll error] ${e.message}`); heartbeat({ pollError: String(e.message).slice(0, 120) }); }
  }, POLL_MS);
})().catch(e => { console.error("FATAL:", e.message); process.exit(1); });
