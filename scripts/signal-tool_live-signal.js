// =============================================================
//  live-signal.js — LIVE signal + execution engine for the LOCKED strategy:
//  "Power-hour Momentum + ADX>20 gate" @ flat 5 MNQ (journal (k)/(m)/(q)).
//
//  TWO MODES (set by the ARMED env var):
//   • DRY-RUN (default, ARMED unset): logs "WOULD ENTER/EXIT", posts charts to
//     Discord, places NO orders. Identical signal logic to the backtest.
//   • ARMED (ARMED=1): places REAL bracket orders via projectx-orders.js on the
//     eval account — fully automatic — and posts the same charts to Discord.
//
//  Signal: reuses lab-new4.js's buildAll + ADX(14)>20 gate verbatim (no drift).
//  Window: enters only 15:00-15:45 ET, flat by 16:00 ET.
//  Armed safety: server-side OCO bracket (stop+target) on every entry, single
//   position, day-stop at 80% of the DLL, max 3 trades/day, EOD auto-flatten,
//   broker-position reconciliation on startup, and order errors are alerted not
//   swallowed. Orders are FINAL (TopStep) — automation is for eval/Combine only
//   (barred on Live Funded). Runs on THIS personal device (no VPS/VPN).
//
//  Run:  node live-signal.js                 (DRY-RUN live loop)
//        node live-signal.js --once          (evaluate latest bars once, exit)
//        ARMED=1 node live-signal.js          (LIVE auto-trading loop)
// =============================================================
"use strict";

const fs = require("fs");
const path = require("path");
require("./public/indicators.js");
const Lab = require("./lab-new4.js");
const Yahoo = require("./yahoo.js");
const PX = require("./projectx.js");
const Orders = require("./projectx-orders.js");
const Notify = require("./notify.js");
const { renderTradeChart } = require("./chart.js");
const I = globalThis.Indicators;

// ---- config: volatility-based position sizing (caps per-trade $ risk) ----
const CONTRACTS = parseInt(process.env.MAX_CONTRACTS || "5", 10);  // MAX MNQ contracts (never exceed)
const PV = 2;                   // $ per point per 1 MNQ
const RISK_CAP = parseInt(process.env.RISK_CAP || "300", 10);      // max $ risk/trade -> shrinks size on high-ATR days
// size = floor(RISK_CAP / (stopPts * $2)), clamped to 1..CONTRACTS. On normal ATR this = 5 MNQ;
// on a volatile day (wide ATR stop) it auto-shrinks so one loss can't gut the daily limit. (journal a13/a14)
function sizeFor(stopPts) {
  return Math.max(1, Math.min(CONTRACTS, Math.floor(RISK_CAP / Math.max(1, stopPts * PV))));
}
const ADX_GATE = 20;            // entry only when ADX(14) > 20
const PH_START = 900, PH_END = 945;  // power-hour window in ET minutes (15:00-15:45)
const RTH_END = 960;            // 16:00 ET — flat by close
const POLL_MS = 60_000;         // live loop: check for a new closed bar every 60s
const FEED = process.env.FEED || "projectx";   // "projectx" (TopstepX, verified) | "yahoo" (fallback, no creds)
const LOG = path.join(__dirname, "logs", "live-signals.jsonl");
const STATE_FILE = path.join(__dirname, ".live-state.json");  // crash-safe virtual position
const HEARTBEAT_FILE = path.join(__dirname, ".heartbeat");    // liveness ping for the dashboard
const CHART_DIR = path.join(__dirname, "logs", "charts");     // saved trade chart PNGs (dashboard)
const CHART_LOOKBACK = 70;      // candles drawn on the Discord chart image
const MAX_BAR_AGE = 600;        // seconds: refuse to act on data older than this (stale-feed guard).
                                // 5-min bars are open-timestamped, so a freshly-closed bar is already
                                // ~300s old + feed delay; 600s allows a normal bar but still rejects a
                                // feed that's frozen / missed 2+ bars.

// ---- KILL-SWITCH: a `.disarm` file forces dry-run even when launched ARMED=1.
// The practice smoke test writes this file if its live round-trip FAILS, so a
// broken order path can never fire on the eval. It is honored both at startup
// (below) and live on every poll (in processLatest). Delete .disarm + restart to re-arm.
const DISARM_FILE = path.join(__dirname, ".disarm");
function isDisarmed() { try { return fs.existsSync(DISARM_FILE); } catch { return false; } }

// ---- ARM SWITCH: live order placement only when ARMED=1 (else DRY-RUN) ----
// TopStep permits API automation on eval/Combine accounts (barred on Live Funded);
// keep ACCOUNT_ID pointed at the eval. Default = the $50K Combine (journal (t)).
const ARMED = ((process.env.ARMED || "").trim() === "1") && !isDisarmed();
const DRY_RUN = !ARMED;
let disarmNotified = false;   // post the "disarmed, skipped entry" Discord alert only once
const TRADE_SYMBOL = process.env.PROJECTX_TRADE_SYMBOL || "MNQ";
const ACCOUNT_ID = parseInt(process.env.PROJECTX_ACCOUNT_ID || "24717879", 10); // 50K Combine eval (new, after a14 blowup)

// ---- HARD risk guardrails (protect the eval; orders honor these before firing) ----
const DLL = Lab.DLL || 1000;          // daily loss limit ($)
const DAY_STOP = -1 * parseInt(process.env.DAY_STOP || "600", 10);  // stop opening NEW trades once down this much
const MAX_TRADES_DAY = 3;             // cap re-entries within a day
// Daily-loss guarantee: worst case = |DAY_STOP| + RISK_CAP (the trade that crosses the stop)
// = $600 + $300 = $900 < $1000. A $1k losing day is mathematically blocked. (journal a17)

// ---- EVAL-PASS alert: one-time Discord ping when the profit target is hit ----
const START_BALANCE = parseInt(process.env.START_BALANCE || "50000", 10); // 50K Combine start
const PROFIT_TARGET = parseInt(process.env.PROFIT_TARGET || "3000", 10);  // +$3,000 to pass
const PASS_BALANCE = START_BALANCE + PROFIT_TARGET;                        // = $53,000
const PASS_FLAG = path.join(__dirname, ".eval-passed");                    // fire-once guard

let accountId = ACCOUNT_ID, tradeContractId = null;   // resolved at startup when armed
let day = { key: null, realized: 0, trades: 0 };       // per-ET-day risk counters
function rollDay(key) { if (day.key !== key) day = { key, realized: 0, trades: 0 }; }

const f = (x, d = 2) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));
const money = (x) => (x >= 0 ? "+$" : "-$") + f(Math.abs(x), 0);
function audit(rec) {
  fs.mkdirSync(path.dirname(LOG), { recursive: true });
  fs.appendFileSync(LOG, JSON.stringify({ ts: new Date().toISOString(), ...rec }) + "\n");
}

// liveness ping the dashboard reads to tell "alive" from "stuck/dead".
function writeHeartbeat(extra = {}) {
  try {
    fs.writeFileSync(HEARTBEAT_FILE, JSON.stringify({
      ts: new Date().toISOString(), pid: process.pid, armed: ARMED,
      openPos: !!openPos, dayRealized: day.realized, dayTrades: day.trades, ...extra,
    }));
  } catch (e) { console.error("[heartbeat] write failed:", e.message); }
}

// Discord alert on a fatal crash (the launcher restarts the process afterwards).
function crashAlert(kind, e) {
  const msg = String((e && (e.stack || e.message)) || e);
  console.error(`[${kind}]`, msg);
  Notify.postJSON({ embeds: [{
    title: "🛑 Bot CRASHED", color: 0xe74c3c,
    description: `**${kind}:** ${msg.slice(0, 350)}\n\nThe launcher will restart it in ~15s.`,
    footer: { text: new Date().toISOString() },
  }] }).catch(() => {});
  setTimeout(() => process.exit(1), 1500); // give the post a moment to flush
}

// Post a once-per-day end-of-session recap to Discord after the power hour closes.
let lastRecapKey = null;
function maybeRecap(c) {
  if (c.mins < RTH_END || lastRecapKey === c.key) return;
  lastRecapKey = c.key;
  if (day.trades === 0) return; // nothing happened today — stay quiet
  Notify.postJSON({ embeds: [{
    title: `📅 Daily recap — ${c.key}`,
    color: day.realized >= 0 ? 0x2ecc71 : 0xe74c3c,
    fields: [
      { name: "Trades", value: String(day.trades), inline: true },
      { name: "Day P&L", value: money(day.realized), inline: true },
      { name: "Mode", value: ARMED ? "LIVE" : "DRY-RUN", inline: true },
    ],
    footer: { text: `${ARMED ? `acct ${accountId} · ` : ""}${CONTRACTS} MNQ · power-hour+ADX gate` },
  }] }).catch(() => {});
}
// One-time celebration: when the live account balance reaches the +$3,000 target,
// post a Discord alert and write `.eval-passed` so it never fires twice. Read-only
// (PX.getAccounts). Only runs ARMED, and only while flat so we read REALIZED balance
// (an open winner's unrealized swing can't trip it early).
let passNotified = false;
async function checkEvalPass() {
  if (!ARMED || passNotified || openPos) return;
  try { if (fs.existsSync(PASS_FLAG)) { passNotified = true; return; } } catch {}
  let acct;
  try {
    const accts = await PX.getAccounts();
    acct = accts.find((a) => a.id === accountId);
  } catch { return; } // transient API error — retry next poll
  if (!acct || typeof acct.balance !== "number" || acct.balance < PASS_BALANCE) return;
  passNotified = true;
  const profit = acct.balance - START_BALANCE;
  try { fs.writeFileSync(PASS_FLAG, `passed ${new Date().toISOString()} · balance $${acct.balance}\n`); } catch {}
  audit({ kind: "EVAL_PASSED", balance: acct.balance, profit });
  console.log(`*** EVAL PASSED *** balance $${acct.balance} (${money(profit)})`);
  Notify.postJSON({ embeds: [{
    title: "🎉🏆 EVAL PASSED — +$3,000 profit target hit!",
    color: 0xffd700,
    description: `Account **${acct.name || accountId}** reached **$${acct.balance.toLocaleString()}** — that's **${money(profit)}** profit, clearing the ${money(PROFIT_TARGET)} Combine target.\n\n**Next:** confirm in your TopStep dashboard that the account is funded (check any remaining minimum-trading-day requirement). ⚠️ Automation is **not allowed on the Live Funded account** — consider stopping the bot once you advance.`,
    footer: { text: `acct ${accountId} · ${new Date().toISOString()}` },
  }] }).catch(() => {});
}

function etClock(t) { const p = Lab.etParts(t); return { mins: p.mins, day: p.day, key: p.k }; }
function inRTH(t) { const c = etClock(t); return c.day !== 0 && c.day !== 6 && c.mins >= 570 && c.mins < RTH_END; }

// ---- feed adapters: return ascending [{t,o,h,l,c,v}] of CLOSED bars ----
const feeds = {
  async yahoo() { return Yahoo.fetchBars({ interval: "5m", range: "5d" }); },
  async projectx() {
    // Real TopstepX feed via projectx.js (DATA-ONLY: auth + retrieveBars, no orders).
    // MNQ = the micro we size in; sim data subscription (live=false) for the eval account.
    return PX.fetchBars({ unitNumber: 5, lookbackDays: 5, contract: "MNQ", live: false });
  },
};

// compute the gated Power-hour signal on a bar window; return the signal at the
// latest CLOSED bar (or null). Reuses lab-new4's buildAll verbatim.
function gatedSignalAt(bars) {
  const last = bars.length - 1;
  const high = bars.map((b) => b.h), low = bars.map((b) => b.l), close = bars.map((b) => b.c);
  const adx = I.dmi(high, low, close, 14, 14).adx;
  const sig = Lab.buildAll(bars).powerHour[last];
  const gated = sig && adx[last] != null && adx[last] > ADX_GATE ? sig : null;
  return { last, sig: gated, adx: adx[last] };
}

// ---- crash-safe virtual-position state (survives restarts mid-trade) ----
// Persisted so the always-on background task never double-enters or loses an
// open virtual position across a reboot / restart during the power hour.
function loadState() {
  try { return JSON.parse(fs.readFileSync(STATE_FILE, "utf8")); } catch { return {}; }
}
function saveState(s) {
  try { fs.writeFileSync(STATE_FILE, JSON.stringify(s)); } catch (e) { console.error("[state] save failed:", e.message); }
}

// in-memory virtual position (dry-run only), hydrated from disk on start
let openPos = loadState().openPos || null;

// ---- Discord chart notifications (fire-and-forget; never blocks the loop) ----
const DISCORD_GREEN = 0x2ecc71, DISCORD_RED = 0xe74c3c, DISCORD_BLUE = 0x2980b9, DISCORD_PURPLE = 0x8e44ad;
function notifyTrade(kind, bars, info) {
  // build the embed text + render the chart PNG, then upload. Any failure is
  // logged inside notify.js and swallowed here so trading is never interrupted.
  try {
    const png = renderTradeChart(bars, {
      lookback: CHART_LOOKBACK, dir: info.dir,
      entry: info.entry, stop: info.stop, target: info.target,
      entryT: info.entryT, exit: info.exit, exitT: info.exitT,
    });
    // persist the PNG so the local dashboard can show it inline (keyed by bar time)
    try { fs.mkdirSync(CHART_DIR, { recursive: true }); fs.writeFileSync(path.join(CHART_DIR, `${info.barT}-${kind}.png`), png); } catch {}
    const side = info.dir === 1 ? "LONG" : "SHORT";
    const isEntry = kind === "ENTRY";
    const color = isEntry ? (info.dir === 1 ? DISCORD_GREEN : DISCORD_RED)
                          : (info.pnl >= 0 ? DISCORD_GREEN : DISCORD_RED);
    const fields = isEntry
      ? [
          { name: "Side", value: side, inline: true },
          { name: "Size", value: `${info.size || CONTRACTS} MNQ`, inline: true },
          { name: "Entry", value: f(info.entry), inline: true },
          { name: "Stop", value: f(info.stop), inline: true },
          { name: "Target", value: f(info.target), inline: true },
          { name: "Risk / Reward", value: `${money(-info.risk)} / ${money(info.reward)}`, inline: true },
        ]
      : [
          { name: "Exit reason", value: String(info.why), inline: true },
          { name: "Exit", value: f(info.exit), inline: true },
          { name: "Points", value: f(info.pts), inline: true },
          { name: "P&L", value: money(info.pnl), inline: true },
          { name: "Side", value: side, inline: true },
          { name: "Size", value: `${info.size || CONTRACTS} MNQ`, inline: true },
        ];
    const verb = ARMED ? (isEntry ? "ENTERED" : "EXITED") : (isEntry ? "WOULD ENTER" : "WOULD EXIT");
    const title = isEntry ? `🟢 ${verb} ${side} — Power-hour+ADX gate`
                          : `🔴 ${verb} (${info.why}) — ${money(info.pnl)}`;
    const tag = ARMED ? `LIVE · vol-sized ≤${CONTRACTS} MNQ · acct ${accountId}` : "DRY-RUN · no order sent";
    const payload = {
      embeds: [{
        title, color, fields,
        image: { url: "attachment://chart.png" },
        footer: { text: `${tag} · ${new Date(info.barT * 1000).toISOString()}` },
      }],
    };
    Notify.postImage(payload, png, "chart.png").catch(() => {});
  } catch (e) { console.error("[notify] chart build failed:", e.message); }
}

function alertFail(phase, msg, barT) {
  audit({ kind: "ORDER_ERROR", phase, error: msg, barT });
  Notify.postJSON({ embeds: [{ title: `⚠️ ${phase} order FAILED`, color: DISCORD_RED, description: String(msg).slice(0, 400), footer: { text: new Date((barT || Date.now() / 1000) * 1000).toISOString() } }] }).catch(() => {});
}

// process the latest closed bar: manage an open position, else look for entry.
// ARMED -> places real bracket orders via projectx-orders.js; else dry-run sim.
// `enteredThisBar` mirrors the backtest (exits are checked from entry+1, never the entry bar).
async function processLatest(bars) {
  const i = bars.length - 1, b = bars[i], c = etClock(b.t);
  const stamp = new Date(b.t * 1000).toISOString();
  rollDay(c.key);
  let enteredThisBar = false;

  // ---- entry: only in the power-hour window, flat, with a gated signal ----
  const dayStopped = ARMED && (day.realized <= DAY_STOP || day.trades >= MAX_TRADES_DAY);
  if (!openPos && !dayStopped && c.mins >= PH_START && c.mins <= PH_END && inRTH(b.t)) {
    const { sig } = gatedSignalAt(bars);
    if (sig) {
      const stopPts = Math.abs(sig.entry - sig.stop), targetPts = Math.abs(sig.target - sig.entry);
      const size = sizeFor(stopPts);   // volatility-based: auto-shrink on wide-ATR (high-vol) days
      const risk$ = stopPts * size * PV, reward$ = targetPts * size * PV;
      const side = sig.dir === 1 ? "LONG" : "SHORT";
      const note = { dir: sig.dir, entry: sig.entry, stop: sig.stop, target: sig.target, risk: risk$, reward: reward$, size, entryT: b.t, barT: b.t };
      if (ARMED && isDisarmed()) {
        // Kill-switch tripped (e.g. smoke test failed). Do NOT place a real order
        // and do NOT simulate one — just skip this entry and alert once.
        console.log(`[${stamp}] DISARMED (.disarm present) — skipping ${side} entry, NO order placed.`);
        audit({ kind: "DISARMED_SKIP", dir: side, entry: sig.entry, barT: b.t });
        if (!disarmNotified) {
          disarmNotified = true;
          Notify.postJSON({ embeds: [{
            title: "🛑 Bot DISARMED — entry skipped",
            description: `A gated ${side} signal fired but the \`.disarm\` kill-switch is set, so **no order was placed** on acct ${accountId}. Delete \`.disarm\` and restart to re-arm.`,
            color: DISCORD_RED, timestamp: new Date().toISOString(),
          }] }).catch(() => {});
        }
      } else if (ARMED) {
        const ageSec = Date.now() / 1000 - b.t;
        if (ageSec > MAX_BAR_AGE) {
          // Stale-feed guard: never act on data we can't trust as current.
          console.error(`[${stamp}] STALE FEED (${Math.round(ageSec)}s old) — skipping ${side} entry.`);
          alertFail("Entry", `stale feed: latest bar ${Math.round(ageSec)}s old (> ${MAX_BAR_AGE}s) — entry skipped`, b.t);
        } else {
          const tag = `ph-${c.key}-${b.t}`;
          try {
            const res = await Orders.placeBracketMarket({ accountId, contractId: tradeContractId, dir: sig.dir, size, stopPts, targetPts, tag });
            // capture the ACTUAL fill so P&L + slippage are real, not the intended price
            let fill = sig.entry;
            try {
              const ps = await Orders.searchOpenPositions(accountId);
              const p = ps.find((p) => p.contractId === tradeContractId && p.size !== 0);
              if (p && isFinite(p.averagePrice)) fill = p.averagePrice;
            } catch { /* fall back to intended entry */ }
            const slippage = (sig.dir === 1 ? 1 : -1) * (fill - sig.entry);
            openPos = { dir: sig.dir, entry: fill, intended: sig.entry, slippage, stop: sig.stop, target: sig.target, size, entryDay: c.key, entryT: b.t, orderId: res.orderId, tag, live: true };
            enteredThisBar = true; day.trades++;
            console.log(`[${stamp}] ENTERED ${side} (orderId ${res.orderId}) fill ${f(fill)} (intended ${f(sig.entry)}, slip ${f(slippage)})  stop ${f(sig.stop)}  target ${f(sig.target)}  ${size} MNQ (vol-sized, risk ${money(-risk$)})  *** LIVE ***`);
            audit({ kind: "ORDER_ENTRY", dir: side, entry: fill, intended: sig.entry, slippage, stop: sig.stop, target: sig.target, size, risk: risk$, orderId: res.orderId, tag, barT: b.t });
            saveState({ openPos });
            notifyTrade("ENTRY", bars, { ...note, entry: fill });
          } catch (e) {
            console.error(`[${stamp}] ENTRY ORDER FAILED: ${e.message}`);
            alertFail("Entry", e.message, b.t);
          }
        }
      } else {
        openPos = { dir: sig.dir, entry: sig.entry, stop: sig.stop, target: sig.target, size, entryDay: c.key, entryT: b.t };
        enteredThisBar = true;
        console.log(`[${stamp}] WOULD ENTER ${side}  @ ${f(sig.entry)}  stop ${f(sig.stop)}  target ${f(sig.target)}  ` +
          `${size} MNQ (vol-sized)  risk ${money(-risk$)} / reward ${money(reward$)}   (DRY-RUN, no order sent)`);
        audit({ kind: "INTENT_ENTRY", dir: side, entry: sig.entry, stop: sig.stop, target: sig.target, size, risk: risk$, barT: b.t });
        saveState({ openPos });
        notifyTrade("ENTRY", bars, note);
      }
    }
  }

  // ---- exit management (skip the very bar we entered, like the backtest) ----
  if (openPos && !enteredThisBar) {
    const isLong = openPos.dir === 1;
    const eod = (c.key !== openPos.entryDay || !inRTH(b.t));

    if (ARMED) {
      // The broker-side OCO bracket owns stop/target. We poll the real position:
      //   - position gone  -> bracket already filled (stop/target) -> report it.
      //   - still open + EOD -> we actively flatten (market close + cancel legs).
      //   - still open, intraday -> nothing to do; broker manages.
      let stillOpen = true;
      try {
        const positions = await Orders.searchOpenPositions(accountId);
        stillOpen = positions.some((p) => p.contractId === tradeContractId && p.size !== 0);
      } catch (e) { console.error(`[${stamp}] position poll failed (will retry next bar): ${e.message}`); return; }

      let exit = null, fr = null;
      if (!stillOpen) {
        if (isLong ? b.l <= openPos.stop : b.h >= openPos.stop) exit = { px: openPos.stop, why: "stop" };
        else if (isLong ? b.h >= openPos.target : b.l <= openPos.target) exit = { px: openPos.target, why: "target" };
        else exit = { px: b.c, why: "closed" };
      } else if (eod) {
        try { fr = await Orders.flatten(accountId, tradeContractId); }
        catch (e) { console.error(`[${stamp}] EOD flatten failed: ${e.message}`); alertFail("EOD-flatten", e.message, b.t); return; }
        exit = { px: bars[i - 1].c, why: "EOD/RTH-close" };
      }
      if (exit) {
        const sz = openPos.size || CONTRACTS;
        const pts = isLong ? exit.px - openPos.entry : openPos.entry - exit.px;
        const pnl = pts * sz * PV;
        day.realized += pnl;
        console.log(`[${stamp}] EXITED (${exit.why}) ~${f(exit.px)}  ${f(pts)} pts  ${money(pnl)}  *** LIVE ***  dayP&L ${money(day.realized)}${fr ? ` [flatten closed=${fr.closed} cancelled=${fr.cancelled}]` : ""}`);
        audit({ kind: "ORDER_EXIT", why: exit.why, exit: exit.px, pts, pnl, size: sz, dayRealized: day.realized, flatten: fr, barT: b.t });
        notifyTrade("EXIT", bars, { dir: openPos.dir, entry: openPos.entry, stop: openPos.stop, target: openPos.target, size: sz, entryT: openPos.entryT, exit: exit.px, exitT: b.t, why: exit.why, pts, pnl, barT: b.t });
        openPos = null; saveState({ openPos: null });
      }
    } else {
      // DRY-RUN: simulate the exit exactly like the backtest.
      let exit = null;
      if (eod) exit = { px: bars[i - 1].c, why: "EOD/RTH-close" };
      else if (isLong ? b.l <= openPos.stop : b.h >= openPos.stop) exit = { px: openPos.stop, why: "stop" };
      else if (isLong ? b.h >= openPos.target : b.l <= openPos.target) exit = { px: openPos.target, why: "target" };
      if (exit) {
        const sz = openPos.size || CONTRACTS;
        const pts = isLong ? exit.px - openPos.entry : openPos.entry - exit.px;
        const pnl = pts * sz * PV;
        console.log(`[${stamp}] WOULD EXIT (${exit.why}) @ ${f(exit.px)}  ${f(pts)} pts  ${money(pnl)}   (DRY-RUN)`);
        audit({ kind: "INTENT_EXIT", why: exit.why, exit: exit.px, pts, pnl, size: sz, barT: b.t });
        notifyTrade("EXIT", bars, { dir: openPos.dir, entry: openPos.entry, stop: openPos.stop, target: openPos.target, size: sz, entryT: openPos.entryT, exit: exit.px, exitT: b.t, why: exit.why, pts, pnl, barT: b.t });
        openPos = null;
        saveState({ openPos: null });
      }
    }
  }
}

async function getBars() {
  if (!feeds[FEED]) throw new Error(`Unknown FEED="${FEED}". Use "yahoo" or "projectx".`);
  const bars = await feeds[FEED]();
  return bars.filter((b) => b && isFinite(b.c)).sort((a, b) => a.t - b.t);
}

(async function main() {
  const once = process.argv.includes("--once");
  const demo = process.argv.includes("--demo");
  const mode = ARMED ? "*** ARMED — LIVE ORDERS ***" : "DRY-RUN (no orders)";
  console.log(`LIVE ${mode} — Power-hour + ADX>${ADX_GATE} gate @ ≤${CONTRACTS} MNQ (vol-sized, $${RISK_CAP}/trade cap).  feed=${FEED}  ARMED=${ARMED}`);
  console.log(`Power hour = 15:00-15:45 ET. Audit -> ${LOG}`);
  if (ARMED) console.log(`Account ${accountId} · ${TRADE_SYMBOL} · guards: day-stop ${money(DAY_STOP)} / max ${MAX_TRADES_DAY} trades/day. Orders are FINAL.`);
  console.log("");

  let bars = await getBars();
  if (!bars.length) { console.error("No bars from feed."); process.exit(1); }
  const lastClosed = bars[bars.length - 1];
  console.log(`Loaded ${bars.length} bars; latest closed ${new Date(lastClosed.t * 1000).toISOString()} (ET min ${etClock(lastClosed.t).mins}).`);

  // --demo: fabricate a sample entry + exit on the latest bars and post BOTH to
  // Discord, to verify the chart renderer + webhook end-to-end (no state touched).
  if (demo) {
    const eIdx = Math.max(0, bars.length - 6), xIdx = bars.length - 1;
    const e = bars[eIdx], x = bars[xIdx];
    const entry = e.c, dir = 1, atr = Math.max(5, (e.h - e.l) || 10);
    const stop = entry - 1.2 * atr, target = entry + 1.8 * atr, exit = x.c;
    const pts = exit - entry, pnl = pts * CONTRACTS * PV;
    console.log("[--demo] posting sample ENTRY + EXIT charts to Discord...");
    notifyTrade("ENTRY", bars, { dir, entry, stop, target, risk: Math.abs(entry - stop) * CONTRACTS * PV, reward: Math.abs(target - entry) * CONTRACTS * PV, entryT: e.t, barT: e.t });
    notifyTrade("EXIT", bars, { dir, entry, stop, target, entryT: e.t, exit, exitT: x.t, why: "demo", pts, pnl, barT: x.t });
    await new Promise((r) => setTimeout(r, 4000)); // let the async posts flush before exit
    console.log("[--demo] done — check your Discord channel for two chart embeds.");
    return;
  }

  // ---- ARMED startup: resolve the tradable contract, verify the account, and
  // reconcile any pre-existing broker position so we never double-trade. ----
  if (ARMED) {
    tradeContractId = await Orders.resolveTradeContract(TRADE_SYMBOL, false);
    const accts = await PX.getAccounts();
    const acct = accts.find((a) => a.id === accountId);
    if (!acct) throw new Error(`ARMED: account id ${accountId} not found among active accounts — refusing to trade.`);
    if (!acct.canTrade) throw new Error(`ARMED: account ${accountId} (${acct.name}) canTrade=false — refusing to trade.`);
    console.log(`ARMED on "${acct.name}" (id ${accountId}, balance $${acct.balance}). Trade contract ${tradeContractId}.`);
    // reconcile: align openPos with the broker's actual position
    const positions = await Orders.searchOpenPositions(accountId);
    const live = positions.find((p) => p.contractId === tradeContractId && p.size !== 0);
    if (live && !openPos) {
      const c = etClock(lastClosed.t);
      openPos = { dir: live.type === 1 ? 1 : -1, entry: live.averagePrice, stop: null, target: null, entryDay: c.key, entryT: lastClosed.t, orderId: null, adopted: true, live: true };
      console.log(`Reconciled: adopted existing broker position (size ${live.size} @ ${live.averagePrice}). Will flatten at EOD.`);
      Notify.postJSON({ embeds: [{ title: "⚠️ Reconcile: adopted broker position", color: 0xf39c12,
        description: `On startup the broker showed an OPEN ${live.type === 1 ? "LONG" : "SHORT"} (size ${live.size} @ ${live.averagePrice}) with no local state. Adopted it; will flatten at EOD. **It has no stop/target attached** — check manually.`,
        footer: { text: new Date().toISOString() } }] }).catch(() => {});
    } else if (!live && openPos) {
      console.log("Reconciled: broker shows FLAT but state had a position — clearing stale state.");
      Notify.postJSON({ embeds: [{ title: "⚠️ Reconcile: cleared stale position", color: 0xf39c12,
        description: `Local state had an open ${openPos.dir === 1 ? "LONG" : "SHORT"} but the broker is FLAT. Cleared the stale state — no action needed unless you expected a position.`,
        footer: { text: new Date().toISOString() } }] }).catch(() => {});
      openPos = null; saveState({ openPos: null });
    }
  }

  // evaluate the latest bar immediately so a --once run shows current state
  await processLatest(bars);
  await checkEvalPass();   // in case the target was already crossed while the bot was down
  const nowMins = etClock(lastClosed.t).mins;
  if (!openPos && (nowMins < PH_START || nowMins > PH_END)) {
    console.log(`(Outside the 15:00-15:45 ET power-hour window — no entry expected until then. Latest bar ET min ${nowMins}.)`);
  }

  if (once) { console.log("\n--once: evaluated latest bars, exiting."); return; }

  // single-instance guard: if another live loop is already running (alive PID in
  // the lockfile), exit quietly so we never double-poll or double-post to Discord.
  const LOCK = path.join(__dirname, ".live-lock");
  try {
    const prev = parseInt(fs.readFileSync(LOCK, "utf8"), 10);
    if (prev && prev !== process.pid) { try { process.kill(prev, 0); console.log(`Another instance (pid ${prev}) is already running — exiting.`); return; } catch { /* stale lock */ } }
  } catch { /* no lock yet */ }
  fs.writeFileSync(LOCK, String(process.pid));
  const releaseLock = () => { try { if (parseInt(fs.readFileSync(LOCK, "utf8"), 10) === process.pid) fs.unlinkSync(LOCK); } catch {} };
  process.on("exit", releaseLock);
  process.on("SIGINT", () => { releaseLock(); process.exit(0); });

  // live loop: poll, process only when a NEW closed bar appears
  let lastT = lastClosed.t;
  writeHeartbeat({ event: "startup" });
  console.log(`\nLive loop started — polling every ${POLL_MS / 1000}s for new closed 5m bars. Ctrl+C to stop.`);
  Notify.postJSON({
    embeds: [{
      title: ARMED ? "🟥 Bot ONLINE — ARMED (LIVE ORDERS)" : "🟦 Dry-run bot ONLINE",
      color: ARMED ? DISCORD_RED : DISCORD_BLUE,
      description: ARMED
        ? `Power-hour + ADX>${ADX_GATE} gate @ **vol-sized ≤${CONTRACTS} MNQ** (auto-shrinks on high-ATR days, $${RISK_CAP} risk/trade cap) · acct **${accountId}** · **LIVE orders, fully automatic**.\nGuards: day-stop ${money(DAY_STOP)} / max ${MAX_TRADES_DAY} trades/day. Charts posted on every entry & exit.`
        : `Power-hour + ADX>${ADX_GATE} gate @ vol-sized ≤${CONTRACTS} MNQ · feed **${FEED}** · DRY-RUN (no orders).\nWatching 15:00–15:45 ET. I'll post a chart on every entry & exit.`,
      footer: { text: `online ${new Date().toISOString()}${openPos ? " · resumed an open position" : ""}` },
    }],
  }).catch(() => {});
  setInterval(async () => {
    try {
      const fresh = await getBars();
      const latest = fresh[fresh.length - 1];
      const lastBarT = latest ? latest.t : null;
      if (latest && latest.t > lastT) {
        lastT = latest.t;
        await processLatest(fresh);
        maybeRecap(etClock(latest.t));
        await checkEvalPass();   // one-time 🏆 alert if we've crossed the +$3,000 target
      }
      // heartbeat every poll so the dashboard can detect a hung/dead loop
      writeHeartbeat({ lastBarT, lastBarAgeSec: lastBarT ? Math.round(Date.now() / 1000 - lastBarT) : null });
    } catch (e) { console.error(`[poll error] ${e.message}`); writeHeartbeat({ pollError: String(e.message).slice(0, 120) }); }
  }, POLL_MS);
})().catch((e) => crashAlert("FATAL (main)", e));

// Last-resort safety nets: surface a crash to Discord, then exit so the
// self-restart launcher (start-bot.bat) brings the bot back in ~15s.
process.on("uncaughtException", (e) => crashAlert("uncaughtException", e));
process.on("unhandledRejection", (e) => crashAlert("unhandledRejection", e));
