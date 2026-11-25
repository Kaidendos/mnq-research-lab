// =============================================================
//  power-hour-windows.js — robustness battery for strategy #42 "Power-hour
//  momentum" (15:00-15:45 ET, trend-aligned vs EMA200).
//
//  This is the SAME test mean-rev v1.1 passed: slice the 58-day Yahoo NQ=F 5m
//  sample into 5 rolling 30-day windows and check whether the edge is CONSISTENT
//  across all of them, or just concentrated in a lucky stretch. A real edge
//  shows up window after window; an illusion lives in one or two.
//
//  Reuses lab-new4.js's exact strategy code + exit model (imported, not
//  reimplemented). Signals are built ONCE on the full series so EMA200/ATR have
//  full warmup; each window then runs only the trades whose ENTRY falls inside
//  it (intraday trades are flat by EOD, so the whole trade stays in-window).
//
//  Reported at 5 MNQ ($10/pt) and 1 MNQ ($2/pt), with $50K Combine flags
//  (DLL $1,000/day, MLL $2,000 max-drawdown).
//
//  DATA-ONLY / TopStep-compliant: public data read, never places an order.
//  Run:  node power-hour-windows.js
// =============================================================
"use strict";

const fs = require("fs");
const Yahoo = require("./yahoo.js");
const Lab = require("./lab-new4.js");

const KEY = "powerHour";
const DLL = Lab.DLL, MLL = Lab.MLL;
const f = (x, d = 0) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));

// ET calendar date as YYYYMMDD (matches lab-new4's ET Date construction)
function etYmd(s) {
  const d = new Date(new Date(s * 1000).toLocaleString("en-US", { timeZone: "America/New_York" }));
  return d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
}

// the same 5 rolling 30-day windows mean-rev v1.1 was graded on
const WINDOWS = [
  { label: "1  Apr 9 -> May 14", lo: 20260409, hi: 20260514 },
  { label: "2  Apr 17 -> May 22", lo: 20260417, hi: 20260522 },
  { label: "3  Apr 26 -> Jun 2", lo: 20260426, hi: 20260602 },
  { label: "4  May 5 -> Jun 10", lo: 20260505, hi: 20260610 },
  { label: "5  May 13 -> Jun 18", lo: 20260513, hi: 20260618 },
];

// mask a signal array to only fire for entries inside [lo,hi]
function maskToWindow(bars, sig, lo, hi) {
  return sig.map((v, i) => { if (!v) return null; const d = etYmd(bars[i].t); return d >= lo && d <= hi ? v : null; });
}

(async () => {
  let bars = null;
  try { bars = await Yahoo.fetchBars({ interval: "5m", range: "60d" }); }
  catch (e) { console.error(`Yahoo live fetch failed (${e.message}); using cached data/nq-5m.json`); bars = JSON.parse(fs.readFileSync(__dirname + "/data/nq-5m.json", "utf8")); }

  const totalDays = new Set(bars.map((b) => Lab.dayKeyOf(b.t))).size;
  const S = Lab.buildAll(bars);          // build ALL signals once, full warmup
  const sig = S[KEY];

  console.log(`POWER-HOUR (#42) ROBUSTNESS — 5 rolling 30-day windows on Yahoo NQ=F 5m (${totalDays} ET days / ${bars.length} bars).`);
  console.log(`Same battery mean-rev v1.1 passed (0/5 breaches, every window positive). Combine: DLL $${DLL}/day, MLL $${MLL}. Net @5 MNQ ($10/pt) and @1 MNQ ($2/pt).\n`);

  const hdr = "Window".padEnd(20) + "Trd".padStart(4) + "Win%".padStart(6) + "PF".padStart(6) +
    "Net@5".padStart(10) + "Net@1".padStart(9) + "MaxDD@5".padStart(9) + "WrstDay@5".padStart(11) +
    "$3k?".padStart(6) + "5MNQ".padStart(6) + "1MNQ".padStart(6);
  console.log(hdr); console.log("-".repeat(hdr.length));

  const results = [];
  for (const w of WINDOWS) {
    const r = Lab.runSignals(bars, maskToWindow(bars, sig, w.lo, w.hi));
    results.push(r);
    const net5 = r.netPts * 10, net1 = r.netPts * 2, dd5 = r.ddPts * 10;
    const wd5 = Math.abs(r.worstDayPts * 10), wd1 = Math.abs(r.worstDayPts * 2), dd1 = r.ddPts * 2;
    const surv5 = (wd5 < DLL && dd5 < MLL) ? "OK" : (wd5 >= DLL ? "DLL!" : "MLL!");
    const surv1 = (wd1 < DLL && dd1 < MLL) ? "OK" : (wd1 >= DLL ? "DLL!" : "MLL!");
    const hit3k = net5 >= 3000 ? "yes" : "no";
    console.log(
      w.label.padEnd(20) + String(r.n).padStart(4) + (f(r.winRate) + "%").padStart(6) +
      (r.pf === Infinity ? "inf" : f(r.pf, 2)).padStart(6) +
      ((net5 >= 0 ? "+$" : "-$") + f(Math.abs(net5))).padStart(10) +
      ((net1 >= 0 ? "+$" : "-$") + f(Math.abs(net1))).padStart(9) +
      ("$" + f(dd5)).padStart(9) + ("-$" + f(wd5)).padStart(11) +
      hit3k.padStart(6) + surv5.padStart(6) + surv1.padStart(6)
    );
  }

  // verdict
  const allPos = results.every((r) => r.netPts > 0);
  const allPF = results.every((r) => r.pf >= 1.3);
  const breaches5 = results.filter((r) => Math.abs(r.worstDayPts * 10) >= DLL || r.ddPts * 10 >= MLL).length;
  const breaches1 = results.filter((r) => Math.abs(r.worstDayPts * 2) >= DLL || r.ddPts * 2 >= MLL).length;
  const hits = results.filter((r) => r.netPts * 10 >= 3000).length;
  const nets5 = results.map((r) => r.netPts * 10);
  const avg5 = nets5.reduce((s, x) => s + x, 0) / nets5.length;
  const pfs = results.map((r) => r.pf).filter((x) => isFinite(x));

  console.log(`\nVERDICT`);
  console.log(`  Positive in all 5 windows? ${allPos ? "YES" : "NO (" + results.filter((r) => r.netPts > 0).length + "/5)"}`);
  console.log(`  PF >= 1.3 in all 5?        ${allPF ? "YES" : "NO (" + results.filter((r) => r.pf >= 1.3).length + "/5)"}`);
  console.log(`  PF range: ${f(Math.min(...pfs), 2)} -> ${f(Math.max(...pfs), 2)}`);
  console.log(`  Net @5 MNQ range: +$${f(Math.min(...nets5))} -> +$${f(Math.max(...nets5))}   (avg +$${f(avg5)})`);
  console.log(`  Hit $3k inside a 30-day window: ${hits}/5`);
  console.log(`  Combine breaches @5 MNQ: ${breaches5}/5    @1 MNQ: ${breaches1}/5`);
  console.log(`\n  v1.1 baseline on the same 5 windows: 0/5 breaches, all positive, avg ~+$1,605 @5MNQ, PF 1.39->2.40, 1/5 hit $3k.`);
  console.log(`  Caveat: all 5 windows are carved from the SAME spring quarter — they overlap and share regime. Consistency here = not-concentrated-in-one-week; it is NOT multi-regime proof. A non-trending quarter is still untested.`);
})().catch((e) => { console.error("power-hour-windows error:", e.stack || e.message); process.exit(1); });
