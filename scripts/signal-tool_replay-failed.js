// replay-failed.js — reconstruct the trades the ARMED bot TRIED to take today
// (order placement failed with the broker "Auto OCO Brackets" error, so nothing
// actually filled). Replays the exact DRY-RUN state machine from live-signal.js
// over today's real MNQ bars to recover each logical trade + simulate its outcome.
"use strict";
require("./public/indicators.js");
const Lab = require("./lab-new4.js");
const PX = require("./projectx.js");
const Notify = require("./notify.js");
const I = globalThis.Indicators;

const CONTRACTS = 5, PV = 2, RISK_CAP = 300, ADX_GATE = 20;
const PH_START = 900, PH_END = 945, RTH_END = 960;
const sizeFor = (stopPts) => Math.max(1, Math.min(CONTRACTS, Math.floor(RISK_CAP / Math.max(1, stopPts * PV))));
const etClock = (t) => { const p = Lab.etParts(t); return { mins: p.mins, day: p.day, key: p.k }; };
const inRTH = (t) => { const c = etClock(t); return c.day !== 0 && c.day !== 6 && c.mins >= 570 && c.mins < RTH_END; };
const f = (x, d = 2) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));
const money = (x) => (x >= 0 ? "+$" : "-$") + f(Math.abs(x), 0);

(async () => {
  const bars = (await PX.fetchBars({ unitNumber: 5, lookbackDays: 5, contract: "MNQ", live: false }))
    .filter((b) => b && isFinite(b.c)).sort((a, b) => a.t - b.t);

  // causal indicators over the full series (ADX/powerHour value at i depends only on data <= i)
  const high = bars.map((b) => b.h), low = bars.map((b) => b.l), close = bars.map((b) => b.c);
  const adx = I.dmi(high, low, close, 14, 14).adx;
  const ph = Lab.buildAll(bars).powerHour;

  const TODAY = etClock(bars[bars.length - 1].t).key;  // ET day key of the latest bar
  const trades = [];
  let openPos = null;

  for (let i = 0; i < bars.length; i++) {
    const b = bars[i], c = etClock(b.t);
    let enteredThisBar = false;

    // entry: flat, inside power-hour window, gated signal (mirrors processLatest)
    if (!openPos && c.mins >= PH_START && c.mins <= PH_END && inRTH(b.t)) {
      const sig = (ph[i] && adx[i] != null && adx[i] > ADX_GATE) ? ph[i] : null;
      if (sig) {
        const stopPts = Math.abs(sig.entry - sig.stop), targetPts = Math.abs(sig.target - sig.entry);
        const size = sizeFor(stopPts);
        openPos = { dir: sig.dir, entry: sig.entry, stop: sig.stop, target: sig.target, size,
          entryDay: c.key, entryT: b.t, stopPts, targetPts, adx: adx[i] };
        enteredThisBar = true;
      }
    }

    // exit: skip the entry bar, then stop/target/EOD (dry-run sim, like the bot)
    if (openPos && !enteredThisBar) {
      const isLong = openPos.dir === 1;
      const eod = (c.key !== openPos.entryDay || !inRTH(b.t));
      let exit = null;
      if (eod) exit = { px: bars[i - 1].c, why: "EOD/RTH-close" };
      else if (isLong ? b.l <= openPos.stop : b.h >= openPos.stop) exit = { px: openPos.stop, why: "stop" };
      else if (isLong ? b.h >= openPos.target : b.l <= openPos.target) exit = { px: openPos.target, why: "target" };
      if (exit) {
        const pts = isLong ? exit.px - openPos.entry : openPos.entry - exit.px;
        const pnl = pts * openPos.size * PV;
        trades.push({ ...openPos, exit: exit.px, why: exit.why, exitT: b.t, pts, pnl });
        openPos = null;
      }
    }
  }
  if (openPos) {  // still open at end of data
    const last = bars[bars.length - 1], isLong = openPos.dir === 1;
    const pts = isLong ? last.c - openPos.entry : openPos.entry - last.c;
    trades.push({ ...openPos, exit: last.c, why: "still-open(EOD)", exitT: last.t, pts, pnl: pts * openPos.size * PV });
  }

  const todays = trades.filter((t) => t.entryDay === TODAY);
  const dayPnl = todays.reduce((s, t) => s + t.pnl, 0);
  const wins = todays.filter((t) => t.pnl > 0).length;

  console.log(`\n=== Replay for ET day ${TODAY} — ${todays.length} trade(s) the bot tried to take ===`);
  for (const [n, t] of todays.entries()) {
    const side = t.dir === 1 ? "LONG" : "SHORT";
    const eET = new Date(t.entryT * 1000).toLocaleString("en-US", { timeZone: "America/New_York" });
    const xET = new Date(t.exitT * 1000).toLocaleString("en-US", { timeZone: "America/New_York" });
    console.log(`\nTrade ${n + 1}: ${side} ${t.size} MNQ`);
    console.log(`  Entry ${f(t.entry)} @ ${eET}  (ADX ${f(t.adx, 1)})`);
    console.log(`  Stop ${f(t.stop)}  Target ${f(t.target)}`);
    console.log(`  Exit  ${f(t.exit)} (${t.why}) @ ${xET}`);
    console.log(`  ${t.pts >= 0 ? "WIN " : "LOSS"}  ${f(t.pts)} pts  ${money(t.pnl)}`);
  }
  console.log(`\nDay total: ${money(dayPnl)}  (${wins}/${todays.length} winners)`);

  // ---- Discord post (only with --post; otherwise just print for verification) ----
  if (!process.argv.includes("--post")) { console.log("\n(dry: pass --post to send to Discord)"); return; }
  const fields = todays.map((t, n) => {
    const side = t.dir === 1 ? "LONG" : "SHORT";
    const tET = new Date(t.entryT * 1000).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" });
    return {
      name: `Trade ${n + 1}: ${side} ${t.size} MNQ @ ${tET} ET`,
      value: `Entry **${f(t.entry)}** → Exit **${f(t.exit)}** (${t.why})\n`
        + `Stop ${f(t.stop)} · Target ${f(t.target)}\n`
        + `${t.pnl >= 0 ? "✅ **WIN**" : "❌ **LOSS**"} · ${f(t.pts)} pts · **${money(t.pnl)}**`,
      inline: false,
    };
  });
  const ok = await Notify.postJSON({
    embeds: [{
      title: `⚠️ ${todays.length} trade(s) FAILED to place today (${TODAY})`,
      color: dayPnl >= 0 ? 0x2ecc71 : 0xe74c3c,
      description: `The ARMED bot generated ${todays.length} power-hour signal(s) but **every order was rejected** by the broker (\`Brackets cannot be used with Position Brackets — enable Auto OCO Brackets\`), so nothing actually filled.\n\nHad they filled, here's how they would have resolved (simulated on real MNQ bars):`,
      fields,
      footer: { text: `Simulated outcome · would-be day P&L ${money(dayPnl)} · ${wins}/${todays.length} winners · 5K Combine acct 24717879` },
      timestamp: new Date().toISOString(),
    }],
  });
  console.log(ok ? "\nPosted to Discord ✅" : "\nDiscord post failed ❌");
})().catch((e) => { console.error("replay failed:", e.message); process.exit(1); });
