// replay-each.js — reconstruct EACH individual failed entry order from today.
// Drives off the real audit log (live-signals.jsonl): every ORDER_ERROR with
// today's ET day is a distinct entry the bot tried to place. For each, recompute
// the gated signal at that bar and simulate the would-be outcome independently.
"use strict";
const fs = require("fs");
const path = require("path");
require("./public/indicators.js");
const Lab = require("./lab-new4.js");
const PX = require("./projectx.js");
const Notify = require("./notify.js");
const I = globalThis.Indicators;

const CONTRACTS = 5, PV = 2, RISK_CAP = 300, ADX_GATE = 20;
const sizeFor = (stopPts) => Math.max(1, Math.min(CONTRACTS, Math.floor(RISK_CAP / Math.max(1, stopPts * PV))));
const etClock = (t) => { const p = Lab.etParts(t); return { mins: p.mins, day: p.day, key: p.k }; };
const f = (x, d = 2) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));
const money = (x) => (x >= 0 ? "+$" : "-$") + f(Math.abs(x), 0);
const etTime = (t) => new Date(t * 1000).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" });
const inRTH = (t) => { const c = etClock(t); return c.day !== 0 && c.day !== 6 && c.mins >= 570 && c.mins < 960; };

// exact copy of lab-new4 simulateTrade (not exported there): stop/target/EOD, from entry+1
function simulateTrade(bars, entryIdx, sig) {
  const isLong = sig.dir === 1, entry = sig.entry, startDay = etClock(bars[entryIdx].t).key;
  for (let k = entryIdx + 1; k < bars.length; k++) {
    if (etClock(bars[k].t).key !== startDay || !inRTH(bars[k].t)) { const px = bars[k - 1].c; return { pts: isLong ? px - entry : entry - px, exitIdx: k - 1 }; }
    const b = bars[k];
    if (isLong ? b.l <= sig.stop : b.h >= sig.stop) return { pts: isLong ? sig.stop - entry : entry - sig.stop, exitIdx: k };
    if (isLong ? b.h >= sig.target : b.l <= sig.target) return { pts: isLong ? sig.target - entry : entry - sig.target, exitIdx: k };
  }
  const px = bars[bars.length - 1].c; return { pts: isLong ? px - entry : entry - px, exitIdx: bars.length - 1 };
}

(async () => {
  const LOG = path.join(__dirname, "logs", "live-signals.jsonl");
  const lines = fs.readFileSync(LOG, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));

  const bars = (await PX.fetchBars({ unitNumber: 5, lookbackDays: 5, contract: "MNQ", live: false }))
    .filter((b) => b && isFinite(b.c)).sort((a, b) => a.t - b.t);
  const TODAY = etClock(bars[bars.length - 1].t).key;

  const high = bars.map((b) => b.h), low = bars.map((b) => b.l), close = bars.map((b) => b.c);
  const adx = I.dmi(high, low, close, 14, 14).adx;
  const ph = Lab.buildAll(bars).powerHour;
  const idxByT = new Map(bars.map((b, i) => [b.t, i]));

  // every failed entry order from today, in time order
  const fails = lines
    .filter((r) => r.kind === "ORDER_ERROR" && r.phase === "Entry" && etClock(r.barT).key === TODAY)
    .sort((a, b) => a.barT - b.barT);

  console.log(`\n=== ${fails.length} failed entry order(s) today (${TODAY}) ===`);
  const recon = [];
  for (const [n, ev] of fails.entries()) {
    const i = idxByT.get(ev.barT);
    if (i == null) { console.log(`\n#${n + 1} bar ${etTime(ev.barT)} ET — bar not in feed, skipped`); continue; }
    const sig = (ph[i] && adx[i] != null && adx[i] > ADX_GATE) ? ph[i] : null;
    if (!sig) { console.log(`\n#${n + 1} bar ${etTime(ev.barT)} ET — no gated signal recomputed`); continue; }
    const stopPts = Math.abs(sig.entry - sig.stop);
    const size = sizeFor(stopPts);
    const { pts, exitIdx } = simulateTrade(bars, i, sig);  // exact dry-run exit sim
    const pnl = pts * size * PV;
    const isLong = sig.dir === 1;
    const exitB = bars[exitIdx];
    let why = "EOD/RTH-close";
    if (isLong ? exitB.l <= sig.stop : exitB.h >= sig.stop) why = "stop";
    else if (isLong ? exitB.h >= sig.target : exitB.l <= sig.target) why = "target";
    const rec = { n: n + 1, side: isLong ? "LONG" : "SHORT", entryT: ev.barT, entry: sig.entry,
      stop: sig.stop, target: sig.target, size, adx: adx[i], exit: bars[exitIdx].c, exitT: bars[exitIdx].t, why, pts, pnl };
    // exit price for stop/target is the level itself
    if (why === "stop") rec.exit = sig.stop; else if (why === "target") rec.exit = sig.target;
    recon.push(rec);

    console.log(`\n#${n + 1}  ${rec.side} ${size} MNQ  @ ${etTime(ev.barT)} ET   (ADX ${f(adx[i], 1)})`);
    console.log(`   Entry ${f(sig.entry)}  Stop ${f(sig.stop)}  Target ${f(sig.target)}`);
    console.log(`   Exit  ${f(rec.exit)} (${why}) @ ${etTime(rec.exitT)} ET`);
    console.log(`   ${pnl >= 0 ? "WIN " : "LOSS"}  ${f(pts)} pts  ${money(pnl)}`);
  }
  const total = recon.reduce((s, r) => s + r.pnl, 0);
  const wins = recon.filter((r) => r.pnl > 0).length;
  console.log(`\nIf each had filled independently: ${money(total)}  (${wins}/${recon.length} winners)`);

  if (!process.argv.includes("--post")) { console.log("\n(dry: pass --post to send to Discord)"); return; }

  const fields = recon.map((r) => ({
    name: `#${r.n}: ${r.side} ${r.size} MNQ @ ${etTime(r.entryT)} ET  (ADX ${f(r.adx, 1)})`,
    value: `Entry **${f(r.entry)}** → Exit **${f(r.exit)}** (${r.why})\n`
      + `Stop ${f(r.stop)} · Target ${f(r.target)}\n`
      + `${r.pnl >= 0 ? "✅ **WIN**" : "❌ **LOSS**"} · ${f(r.pts)} pts · **${money(r.pnl)}**`,
    inline: false,
  }));
  const ok = await Notify.postJSON({
    embeds: [{
      title: `⚠️ ${recon.length} failed entry orders today (${TODAY})`,
      color: total >= 0 ? 0x2ecc71 : 0xe74c3c,
      description: `Each was rejected by the broker (\`Brackets cannot be used with Position Brackets — enable Auto OCO Brackets\`), so **nothing filled**. Below is each individual attempt with its would-be outcome (simulated on real MNQ bars, each as if filled on its own):`,
      fields,
      footer: { text: `Simulated · ${wins}/${recon.length} winners · combined ${money(total)} · acct 24717879` },
      timestamp: new Date().toISOString(),
    }],
  });
  console.log(ok ? "\nPosted to Discord ✅" : "\nDiscord post failed ❌");
})().catch((e) => { console.error("replay-each failed:", e.message); process.exit(1); });
