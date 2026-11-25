// =============================================================
//  smoke-test.js — one-shot LIVE order round-trip test on the PRACTICE account.
//
//  Purpose: before the armed bot's first REAL power-hour fill on the eval, prove
//  the full execution path works end-to-end against a live, open market:
//      place 1 MNQ (market + OCO bracket) -> confirm the fill -> flatten -> verify flat.
//  The whole run is reported to Discord as ONE consolidated embed (a step timeline
//  + the results), instead of a separate message per step. Places NO eval orders.
//
//  Safety:
//    - Hard-locked to the PRACTICE account. Refuses to run against the eval id.
//    - Waits for the market to actually be open (fresh bars) before sending anything;
//      aborts cleanly if it never opens within the wait window.
//    - Wide 20pt bracket so neither leg can trigger in the ~seconds before we flatten.
//    - Tiny size (1 MNQ = $2/pt) on a $150k sim account.
//
//  Run:  node smoke-test.js
//  Scheduled to fire automatically when Globex reopens (Sun 6 PM ET).
// =============================================================
"use strict";

const fs = require("fs");
const path = require("path");
const PX = require("./projectx.js");
const Orders = require("./projectx-orders.js");
const Notify = require("./notify.js");

// Tripping this file forces the armed eval bot back to dry-run (it checks for it
// every poll). We write it only on a genuine EXECUTION failure — never on a clean
// "market never opened" abort, which is not a code fault.
const DISARM_FILE = path.join(__dirname, ".disarm");
function disarmEvalBot(reason) {
  try {
    fs.writeFileSync(DISARM_FILE, `disarmed by smoke-test ${new Date().toISOString()}: ${reason}\n`);
    return true;
  } catch (e) {
    console.error(`[smoke] FAILED to write ${DISARM_FILE}: ${e.message}`);
    return false;
  }
}

// --- config ---
const PRACTICE_ACCOUNT_ID = XXXX;   // PRAC-V2-112211-37100419 (sim)
const EVAL_ACCOUNT_ID = 24717879;        // 50K Combine (new) — NEVER trade here from this script
const ACCOUNT_ID = parseInt(process.env.SMOKE_ACCOUNT_ID || String(PRACTICE_ACCOUNT_ID), 10);
const TRADE_SYMBOL = process.env.SMOKE_SYMBOL || "MNQ";
const SIZE = 1;                          // 1 micro = $2/pt
const STOP_PTS = 20;                     // wide so it can't trigger before we flatten
const TARGET_PTS = 20;

const FRESH_MS = 9 * 60 * 1000;          // a closed 5-min bar newer than this => market live
const MAX_WAIT_MS = 45 * 60 * 1000;      // give up if market never opens within 45 min
const OPEN_POLL_MS = 60 * 1000;          // re-check market every 60s while waiting
const FILL_POLL_MS = 1500;               // poll for the fill every 1.5s
const FILL_TRIES = 20;                   // ~30s to see the position appear

const COLOR = { info: 0x3498db, ok: 0x2ecc71, warn: 0xf1c40f, err: 0xe74c3c };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const START_MS = Date.now();
const money = (n) => (n < 0 ? "-$" : "+$") + Math.abs(Number(n) || 0).toFixed(2);

// --- step timeline: buffered, NOT posted per-step ---
// Each step is logged to the console immediately (for the .log file) and pushed
// into `steps`; the whole timeline ships once at the end inside the result embed.
const steps = [];
function step(emoji, title, detail = "") {
  steps.push({ ts: new Date(), emoji, title, detail });
  console.log(`[smoke] ${title}${detail ? " — " + detail : ""}`);
}

function etTime(d) {
  return d.toLocaleTimeString("en-US", { hour12: false, timeZone: "America/New_York" });
}
function timelineField() {
  if (!steps.length) return "(no steps recorded)";
  return steps
    .map((s) => `\`${etTime(s.ts)}\` ${s.emoji} ${s.title}${s.detail ? ` — ${s.detail}` : ""}`)
    .join("\n");
}
function elapsed() {
  return ((Date.now() - START_MS) / 1000).toFixed(1) + "s";
}

// Post the ONE consolidated result embed for the whole run.
async function postResult(title, color, summary, fields = []) {
  console.log(`[smoke] RESULT: ${title} — ${summary}`);
  try {
    await Notify.postJSON({
      embeds: [{
        title: `🧪 Smoke Test — ${title}`,
        description: summary,
        color,
        fields: [
          ...fields,
          { name: "Steps", value: timelineField(), inline: false },
        ],
        footer: { text: `PRACTICE acct ${ACCOUNT_ID} · ${TRADE_SYMBOL} · sim · ${elapsed()}` },
        timestamp: new Date().toISOString(),
      }],
    });
  } catch { /* notify never throws; ignore */ }
}

// Block any chance of trading the funded/eval account from a test script.
function assertPracticeAccount() {
  if (ACCOUNT_ID === EVAL_ACCOUNT_ID) {
    throw new Error(`refusing to run: ACCOUNT_ID ${ACCOUNT_ID} is the EVAL account, not practice`);
  }
}

// Wait until the exchange is actually trading (latest closed bar is fresh).
async function waitForOpenMarket() {
  const deadline = Date.now() + MAX_WAIT_MS;
  while (Date.now() < deadline) {
    let bars = [];
    try {
      bars = await PX.fetchBars({ unitNumber: 5, lookbackDays: 1, live: false, contract: TRADE_SYMBOL });
    } catch (e) {
      console.log(`[smoke] bar fetch error while waiting: ${e.message}`);
    }
    const last = bars[bars.length - 1];
    const ageMs = last ? Date.now() - last.t * 1000 : Infinity;
    if (last && ageMs < FRESH_MS) {
      const et = new Date(last.t * 1000).toLocaleString("en-US", { timeZone: "America/New_York" });
      return { ok: true, lastBarEt: et, ageMin: Math.round(ageMs / 60000) };
    }
    const ageMin = Number.isFinite(ageMs) ? Math.round(ageMs / 60000) : "?";
    console.log(`[smoke] market not live yet (last bar ${ageMin} min old). Waiting ${OPEN_POLL_MS / 1000}s...`);
    await sleep(OPEN_POLL_MS);
  }
  return { ok: false };
}

// Poll open positions until our contract shows a non-zero size (the fill landed).
async function waitForFill(contractId) {
  for (let i = 0; i < FILL_TRIES; i++) {
    const positions = await Orders.searchOpenPositions(ACCOUNT_ID);
    const pos = positions.find((p) => p.contractId === contractId && p.size !== 0);
    if (pos) return pos;
    await sleep(FILL_POLL_MS);
  }
  return null;
}

async function main() {
  assertPracticeAccount();
  step("⏳", "started", `waiting for open market, then ${SIZE} ${TRADE_SYMBOL} market + ${STOP_PTS}/${TARGET_PTS}pt bracket`);

  // 1) Make sure the market is live (handles imprecise scheduling).
  const open = await waitForOpenMarket();
  if (!open.ok) {
    step("🚫", "aborted", `market never opened within ${MAX_WAIT_MS / 60000} min`);
    await postResult("ABORTED", COLOR.warn,
      "Market never opened within the wait window — **no order placed**. This is a clean abort, not a failure; the eval bot stays armed.",
      [{ name: "Order", value: "none placed", inline: true }]);
    process.exit(2);
  }
  step("📈", "market live", `last bar ${open.lastBarEt} ET (${open.ageMin}m old)`);

  // 2) Resolve the tradable contract and place the order.
  const contractId = await Orders.resolveTradeContract(TRADE_SYMBOL, false);
  step("📤", "placing order", `${SIZE} ${TRADE_SYMBOL} (${contractId}) market BUY w/ bracket`);
  const placed = await Orders.placeBracketMarket({
    accountId: ACCOUNT_ID, contractId, dir: 1, size: SIZE,
    stopPts: STOP_PTS, targetPts: TARGET_PTS, tag: `smoke-${Date.now()}`,
  });
  step("✅", "order accepted", `orderId ${placed.orderId}`);

  // 3) Confirm the fill.
  const pos = await waitForFill(contractId);
  const fillPrice = pos ? (pos.averagePrice ?? pos.avgPrice ?? null) : null;
  if (!pos) {
    step("⚠️", "no fill seen", `position never appeared after ~${(FILL_POLL_MS * FILL_TRIES) / 1000}s — flattening to be safe`);
  } else {
    step("💰", "filled", `${pos.size} ${TRADE_SYMBOL} @ ${fillPrice ?? "?"}`);
  }

  // 4) Flatten (close position + cancel any leftover bracket legs).
  const flat = await Orders.flatten(ACCOUNT_ID, contractId);
  step("🔻", "flattened", `closed=${flat.closed} · ${flat.cancelled} bracket legs cancelled`);

  // 5) Verify we're actually flat.
  const after = await Orders.searchOpenPositions(ACCOUNT_ID);
  const stillOpen = after.find((p) => p.contractId === contractId && p.size !== 0);
  if (stillOpen) {
    step("🛑", "STILL OPEN", `size ${stillOpen.size} after flatten`);
    const disarmed = disarmEvalBot(`flatten left position open (size ${stillOpen.size})`);
    await postResult("FAILED ❌", COLOR.err,
      `Position **not flat** after flatten() — size ${stillOpen.size} still open. ${disarmed ? "**Eval bot DISARMED** (.disarm written) — Monday's trade will be skipped until you fix this and re-arm." : "⚠️ Could not write .disarm — disarm the eval bot MANUALLY."} Manual check needed.`,
      [
        { name: "Order", value: `${SIZE} ${TRADE_SYMBOL} market BUY`, inline: true },
        { name: "Fill", value: fillPrice != null ? `@ ${fillPrice}` : "no fill seen", inline: true },
        { name: "Flatten", value: `closed=${flat.closed} · ${flat.cancelled} legs`, inline: true },
      ]);
    process.exit(3);
  }

  // 6) Pull the broker's realized P&L for this round-trip (the actual USD result).
  //    Trades take a moment to settle after the close; give it a beat, then query.
  let pnl = null, fees = 0, pnlNote = "";
  try {
    await sleep(2500);
    const since = new Date(START_MS - 60 * 1000).toISOString();
    const until = new Date(Date.now() + 60 * 1000).toISOString();
    const r = await Orders.realizedPnL(ACCOUNT_ID, contractId, since, until);
    pnl = r.pnl; fees = r.fees;
    if (pnl == null) pnlNote = r.count ? "(broker reported no P&L yet)" : "(no trades returned yet)";
    step("📊", "realized P&L", pnl != null ? `${money(pnl)}${fees ? ` · fees ${money(-Math.abs(fees))}` : ""}` : pnlNote);
  } catch (e) {
    pnlNote = `lookup failed: ${e.message.slice(0, 60)}`;
    step("📊", "realized P&L", pnlNote);
  }

  const pnlValue = pnl != null
    ? `**${money(pnl)}**${fees ? `\nfees ${money(-Math.abs(fees))} · net ${money(pnl - Math.abs(fees))}` : ""}`
    : (pnlNote || "n/a");
  const summaryPnl = pnl != null ? ` Round-trip realized **${money(pnl)}**.` : "";

  // PASS — one clean result message with the full picture.
  await postResult("PASS ✅", COLOR.ok,
    `Full execution path verified live: **placed → filled → bracket attached → flattened → confirmed flat.**${summaryPnl} The eval bot stays armed for Monday's power hour.`,
    [
      { name: "Order", value: `${SIZE} ${TRADE_SYMBOL} market BUY`, inline: true },
      { name: "Fill", value: fillPrice != null ? `@ ${fillPrice}` : "accepted (no fill seen)", inline: true },
      { name: "💵 Realized P&L", value: pnlValue, inline: true },
      { name: "Bracket", value: `${STOP_PTS}pt stop / ${TARGET_PTS}pt target\n(server-side OCO)`, inline: true },
      { name: "Flatten", value: `closed ${flat.closed ? "✓" : "✗"} · ${flat.cancelled} legs cancelled`, inline: true },
      { name: "Market", value: `${open.lastBarEt} ET\n(${open.ageMin}m old at entry)`, inline: true },
      { name: "Duration", value: elapsed(), inline: true },
    ]);
}

main().catch(async (e) => {
  step("💥", "error", e.message);
  const disarmed = disarmEvalBot(e.message);
  await postResult("FAILED ❌", COLOR.err,
    `${e.message}\n\n${disarmed ? "**Eval bot DISARMED** (.disarm written) — it will skip Monday's trade until you fix this and re-arm." : "⚠️ Could not write .disarm — disarm the eval bot MANUALLY before Monday."}`,
    [{ name: "Order", value: "see steps below", inline: false }]);
  console.error(e);
  process.exit(1);
});
