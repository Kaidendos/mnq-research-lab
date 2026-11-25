// =============================================================
//  watcher.js — polls the market, runs the chosen strategy on the last
//  CLOSED 5-min bar, and pings Discord (@everyone) when a trade fires.
//  De-duped so the same setup is never posted twice.
//
//  Strategy (STRATEGY env):
//    orb     (default) — Opening-Range Breakout v5, the eval edge.
//    meanrev           — v1.1 mean-reversion (the older keeper).
//
//  Feed: prefers the REAL-TIME ProjectX (TopstepX) sim feed via your API
//  key (projectx.js, data-only). If ProjectX creds are missing or the
//  call fails, it falls back to the DELAYED Yahoo feed automatically so
//  the watcher never goes dark. Bar shape is identical either way, so the
//  signal pipeline below is untouched.
//
//  Webhook is read from env DISCORD_WEBHOOK_URL, else secrets.local.js.
//
//  Run:        node watcher.js            (loop, default every 60s)
//    one-shot: node watcher.js --once
//    test:     node watcher.js --test     (sends a test ping to Discord)
// =============================================================
"use strict";

require("./public/indicators.js");
require("./public/meanrev.js");
require("./public/orb.js");
const MeanRev = globalThis.MeanRev;
const ORB = globalThis.ORB;
const ProjectX = require("./projectx.js");
const fs = require("fs");
const path = require("path");

// Which strategy the watcher runs: "meanrev" (v1.1 — the current-regime
// winner: +$446/MNQ, 71% win, PF 3.71 over the last 11 ProjectX days) or
// "orb" (the trending-market eval edge, which stands down in chop).
//   STRATEGY=orb node watcher.js   to switch back to ORB.
const STRATEGY = (process.env.STRATEGY || "meanrev").toLowerCase();

// Live ORB options: range filter ON by default so alerts skip junk-wide OR
// mornings (keeps a fixed-$ bracket aligned). Override:
//   ORB_RANGE_FILTER=off   /   ORB_MAX_OR_PTS=90  node watcher.js
const ORB_OPTS = {
  useRangeFilter: (process.env.ORB_RANGE_FILTER || "on").toLowerCase() !== "off",
  maxRangePts: Number(process.env.ORB_MAX_OR_PTS || 70),
};

// Which feed actually served the most recent bars. Set inside getBars().
// "projectx" = real-time sim feed; "yahoo" = ~10-min delayed fallback.
let FEED = null;

// ProjectX is REQUIRED for live signals by default — we never want to alert
// (or trade) off ~10-min delayed Yahoo data. If ProjectX is down the watcher
// SKIPS the check instead of falling back. Opt back into the fallback with
//   ALLOW_YAHOO=on node watcher.js
const ALLOW_YAHOO = (process.env.ALLOW_YAHOO || "off").toLowerCase() === "on";

const SYMBOL = process.env.SYMBOL || "NQ=F";
const POLL_MS = Number(process.env.POLL_MS || 15000); // 15s: detect a 5-min bar close fast
const STATE_FILE = path.join(__dirname, ".watcher-state.json");

function getWebhook() {
  if (process.env.DISCORD_WEBHOOK_URL) return process.env.DISCORD_WEBHOOK_URL;
  try {
    return require("./secrets.local.js").discordWebhook;
  } catch {
    return null;
  }
}

// Feed: ProjectX real-time sim data ONLY (by default). Returns null if
// ProjectX is unavailable so the caller can skip rather than act on stale
// data. Yahoo is used only when ALLOW_YAHOO=on is explicitly set.
async function getBars() {
  try {
    // 10 trading-ish days easily seeds EMA200 (~210 bars of 5-min).
    const bars = await ProjectX.fetchBars({ unitNumber: 5, lookbackDays: 10 });
    if (bars.length) {
      if (FEED !== "projectx") console.log("Feed: ProjectX real-time sim data.");
      FEED = "projectx";
      return bars;
    }
    throw new Error("ProjectX returned 0 bars");
  } catch (e) {
    if (!ALLOW_YAHOO) {
      console.warn("ProjectX feed unavailable (" + e.message + ") — skipping (ALLOW_YAHOO not set, refusing delayed data).");
      FEED = null;
      return null;
    }
    if (FEED !== "yahoo") console.warn("ProjectX feed unavailable (" + e.message + ") — falling back to delayed Yahoo (ALLOW_YAHOO=on).");
    FEED = "yahoo";
    return fetchBarsYahoo("5m", "1mo");
  }
}

async function fetchBarsYahoo(interval, range) {
  const url =
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(SYMBOL)}` +
    `?interval=${interval}&range=${range}`;
  const r = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
  if (!r.ok) throw new Error("yahoo " + r.status);
  const res = (await r.json())?.chart?.result?.[0];
  if (!res) throw new Error("yahoo: empty result");
  const ts = res.timestamp || [];
  const q = res.indicators?.quote?.[0] || {};
  const bars = [];
  for (let i = 0; i < ts.length; i++) {
    const o = q.open?.[i], h = q.high?.[i], l = q.low?.[i], c = q.close?.[i];
    if (o == null || h == null || l == null || c == null) continue;
    bars.push({ t: ts[i], o, h, l, c, v: q.volume?.[i] ?? 0 });
  }
  return bars;
}

function loadState() {
  try { return JSON.parse(fs.readFileSync(STATE_FILE, "utf8")); }
  catch { return { lastBarTime: 0 }; }
}
function saveState(s) {
  try { fs.writeFileSync(STATE_FILE, JSON.stringify(s)); } catch {}
}

function fmt(x, d = 2) { return x == null ? "—" : Number(x).toFixed(d); }

function buildPayload(sig) {
  const isBuy = sig.signal === "BUY";
  const color = isBuy ? 0x2ecc71 : 0xe74c3c;
  const dirWord = isBuy ? "BUY  (fade long)" : "SELL  (fade short)";
  const riskMNQ = sig.stopPts * MeanRev.CONFIG.pointValueMNQ;
  const rewardMNQ = sig.tgtPts * MeanRev.CONFIG.pointValueMNQ;
  const riskNQ = sig.stopPts * MeanRev.CONFIG.pointValueNQ;
  const rewardNQ = sig.tgtPts * MeanRev.CONFIG.pointValueNQ;
  const barET = new Date(sig.barTime * 1000).toLocaleString("en-US", { timeZone: "America/New_York" });

  // TopstepX bracket cheat-sheet. NQ tick = 0.25 pt, so offsets in ticks
  // are points / 0.25. Brackets in TopstepX accept either price or ticks.
  const TICK = 0.25;
  const stopTicks = Math.round(sig.stopPts / TICK);
  const tgtTicks = Math.round(sig.tgtPts / TICK);
  const sideWord = isBuy ? "BUY" : "SELL";
  const bracket =
    `**LIMIT ${sideWord}** \`${fmt(sig.entry)}\`\n` +
    `🛑 Stop \`${fmt(sig.stop)}\`  (${stopTicks} ticks)\n` +
    `🎯 Target \`${fmt(sig.target)}\`  (${tgtTicks} ticks)`;

  return {
    content: "@everyone  📈 **GOOD TRADE SIGNAL** (mean-rev v1.1)",
    allowed_mentions: { parse: ["everyone"] },
    embeds: [{
      title: `✅ ${dirWord} — NQ 5-min`,
      description: sig.reason,
      color,
      fields: [
        { name: "Entry (≈)", value: "`" + fmt(sig.entry) + "`", inline: true },
        { name: "Stop",      value: "`" + fmt(sig.stop) + "`",  inline: true },
        { name: "Target (mean)", value: "`" + fmt(sig.target) + "`", inline: true },
        { name: "🎟️ TopstepX bracket (punch this in)", value: bracket, inline: false },
        { name: "Risk",   value: `${fmt(sig.stopPts, 1)} pt  ·  $${fmt(riskMNQ, 0)}/MNQ  ·  $${fmt(riskNQ, 0)}/NQ`, inline: false },
        { name: "Reward", value: `${fmt(sig.tgtPts, 1)} pt  ·  $${fmt(rewardMNQ, 0)}/MNQ  ·  $${fmt(rewardNQ, 0)}/NQ`, inline: false },
        { name: "RSI(2)", value: fmt(sig.rsi, 0), inline: true },
        { name: "ADX",    value: fmt(sig.adx, 0) + " (ranging)", inline: true },
        { name: "Bar (ET)", value: barET, inline: false },
      ],
      footer: { text: FEED === "projectx"
        ? "Real-time TopstepX sim feed — confirm on your chart, then YOU place the order (TopStep-compliant)."
        : "⚠ DELAYED ~10min Yahoo data — confirm on your live chart before acting. You place the order (TopStep-compliant)." },
    }],
  };
}

function buildORBPayload(sig) {
  const isBuy = sig.signal === "BUY";
  const color = isBuy ? 0x2ecc71 : 0xe74c3c;
  const C = ORB.CONFIG;
  const riskMNQ = sig.stopPts * C.pointValueMNQ;
  const riskNQ = sig.stopPts * C.pointValueNQ;
  const barET = new Date(sig.barTime * 1000).toLocaleString("en-US", { timeZone: "America/New_York" });

  const TICK = C.tick;
  const stopTicks = Math.round(sig.stopPts / TICK);
  const sideWord = isBuy ? "BUY" : "SELL";
  const arrow = isBuy ? "▲" : "▼";

  // One-line "do this now" instruction at the top.
  const action = `**${sideWord} now** near \`${fmt(sig.entry)}\`  →  set stop \`${fmt(sig.stop)}\``;

  return {
    content: `@everyone  🚀 **ORB v5 — ${sideWord} the break**`,
    allowed_mentions: { parse: ["everyone"] },
    embeds: [{
      title: `${arrow} ${sideWord}  ·  NQ 5-min  ·  ORB v5`,
      description: action,
      color,
      fields: [
        { name: "🎯 Entry", value: "`" + fmt(sig.entry) + "`", inline: true },
        { name: "🛑 Stop", value: `\`${fmt(sig.stop)}\`  (${stopTicks}t)`, inline: true },
        { name: "Risk / 1 MNQ", value: `$${fmt(riskMNQ, 0)}  (${fmt(sig.stopPts, 1)} pt)`, inline: true },
        { name: "Exit = MANUAL trail (no fixed target)", value: "Once ~+1R, trail ~1R behind and **ride the runner**. Don't cap it.", inline: false },
        { name: "Context", value: `OR \`${fmt(sig.orLow)}\`–\`${fmt(sig.orHigh)}\` (${fmt(sig.orRange, 1)}pt)  ·  VWAP \`${fmt(sig.vwap)}\`  ·  ${barET} ET`, inline: false },
      ],
      footer: { text: FEED === "projectx"
        ? "Real-time TopstepX feed · size on MNQ (1 contract) · YOU place & trail the order (TopStep-compliant)."
        : "⚠ DELAYED Yahoo data · confirm first · YOU place & trail the order (TopStep-compliant)." },
    }],
  };
}

async function postDiscord(payload) {
  const hook = getWebhook();
  if (!hook) throw new Error("no webhook — set DISCORD_WEBHOOK_URL or secrets.local.js");
  const r = await fetch(hook, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error("discord " + r.status + " " + (await r.text()));
}

async function checkOnce() {
  const bars = await getBars();
  if (!bars) { console.log(`[${new Date().toISOString()}] no ProjectX bars — skipped (not acting on delayed data)`); return; }
  if (bars.length < 210) { console.log(`[${new Date().toISOString()}] only ${bars.length} bars — warming up`); return; }
  // Evaluate the last CLOSED bar. ProjectX excludes the partial bar already
  // (last bar is closed → use it); Yahoo's final bar may still be forming → step back one.
  const idx = FEED === "projectx" ? bars.length - 1 : bars.length - 2;

  const sig = STRATEGY === "meanrev"
    ? MeanRev.computeMeanRev(bars, idx)
    : ORB.computeORB(bars, idx, ORB_OPTS);

  const tag = STRATEGY === "meanrev"
    ? `price ${fmt(sig.price)} | ${sig.signal} | RSI ${fmt(sig.rsi, 0)} | ADX ${fmt(sig.adx, 0)}`
    : `price ${fmt(sig.price)} | ${sig.signal} | OR ${fmt(sig.orHigh)}/${fmt(sig.orLow)} | VWAP ${fmt(sig.vwap)}`;
  console.log(`[${new Date().toISOString()}] [${STRATEGY}] ${tag} — ${sig.reason}`);

  if (sig.signal !== "BUY" && sig.signal !== "SELL") return;
  const state = loadState();
  if (sig.barTime <= state.lastBarTime) return; // already alerted this (or older) bar
  const payload = STRATEGY === "meanrev" ? buildPayload(sig) : buildORBPayload(sig);
  await postDiscord(payload);
  saveState({ lastBarTime: sig.barTime, lastSignal: sig.signal });
  console.log(`  ↳ posted ${sig.signal} to Discord (bar ${sig.barTime}).`);
}

async function sendTest() {
  await postDiscord({
    content: "@everyone  🔔 **Test ping** — NQ mean-rev watcher is connected.",
    allowed_mentions: { parse: ["everyone"] },
    embeds: [{ title: "Watcher online", description: "If you can see this, alerts will arrive here when a GOOD trade fires.", color: 0x3498db }],
  });
  console.log("Test ping sent.");
}

// Posts a realistic SAMPLE ORB v5 embed (clearly marked as an example) so
// you can see exactly what a live alert will look like. No live data used.
async function sendOrbDemo() {
  const entry = 30617.0, orHigh = 30615.5, orLow = 30560.0;
  const risk = entry - orLow; // opposite-side stop
  const sample = {
    signal: "BUY", dir: 1,
    entry, stop: orLow, target: entry + ORB.CONFIG.rMult * risk,
    stopPts: risk, tgtPts: ORB.CONFIG.rMult * risk,
    orHigh, orLow, orRange: orHigh - orLow, vwap: 30590.25,
    price: entry, barTime: Math.floor(Date.now() / 1000),
    reason: "STRONG break ABOVE the opening range (vol surge + strong close + above VWAP) -> LONG, trail the runner",
  };
  FEED = "projectx"; // demo reflects the real-time feed the live watcher uses
  const payload = buildORBPayload(sample);
  payload.content = "🧪 **[EXAMPLE — not a live signal]**  this is what a real ORB v5 alert looks like";
  payload.allowed_mentions = { parse: [] }; // don't @everyone for a demo
  await postDiscord(payload);
  console.log("Sample ORB embed sent to Discord.");
}

(async () => {
  const arg = process.argv[2];
  if (arg === "--test") { await sendTest(); return; }
  if (arg === "--test-orb") { await sendOrbDemo(); return; }
  if (arg === "--once") { await checkOnce(); return; }

  console.log(`NQ watcher running — strategy: ${STRATEGY.toUpperCase()}, poll ${POLL_MS}ms.`);
  console.log("Webhook:", getWebhook() ? "configured" : "MISSING (set DISCORD_WEBHOOK_URL or secrets.local.js)");
  const tick = async () => { try { await checkOnce(); } catch (e) { console.error("check error:", e.message); } };
  await tick();
  setInterval(tick, POLL_MS);
})();
