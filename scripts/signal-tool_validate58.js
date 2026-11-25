// =============================================================
//  validate58.js — out-of-sample test of batch-2's TOP 3 on the 58-day chart.
//
//  The 13-day lab is a tiny, single-regime sample. This re-runs the 3 best
//  ideas (Inside-bar breakout, Heikin-Ashi flip, MACD-histogram cross) on the
//  FREE ~58-day Yahoo NQ=F 5m feed to see whether the edge survives a longer,
//  mixed-regime window. Same exact strategy code (reused from lab-new2.js) and
//  same fair exit model. Reported at 5 MNQ ($10/pt) with Combine flags.
//
//  NQ=F vs MNQ: identical index, point behavior transfers 1:1; only $/pt scale
//  differs and we already price in MNQ ($2/pt). So edge metrics are valid.
//
//  DATA-ONLY / TopStep-compliant: public data read, never places an order.
//  Run:  node validate58.js
// =============================================================
"use strict";

const Yahoo = require("./yahoo.js");
const Lab = require("./lab-new2.js");

const TOP3 = ["insideBar", "haFlip", "macdHist"]; // batch-2 #5, #19, #11
const f = (x, d = 0) => (x == null || !isFinite(x) ? "—" : Number(x).toFixed(d));

// 13-day baseline (from batch 2) so we can see hold-up at a glance.
const BASE13 = {
  insideBar: { winRate: 41, pf: 1.88, net: 12910 },
  haFlip: { winRate: 52, pf: 1.49, net: 12239 },
  macdHist: { winRate: 52, pf: 1.66, net: 7327 },
};

(async () => {
  const bars = await Yahoo.fetchBars({ interval: "5m", range: "60d" });
  if (!bars.length) throw new Error("Yahoo returned 0 bars");
  const days = new Set(bars.map((b) => Lab.dayKeyOf(b.t))).size;
  const { S } = Lab.buildAll(bars);
  const PV = Lab.PV, DLL = Lab.DLL, MLL = Lab.MLL;

  console.log(`OUT-OF-SAMPLE VALIDATION — 58-day chart (Yahoo NQ=F, ${days} ET days / ${bars.length} 5m bars). Sized ${Lab.SIZE} MNQ ($${PV}/pt).`);
  console.log(`Same strategy code + fair exit model as the 13-day lab. Combine: DLL $${DLL}/day, MLL $${MLL}.\n`);
  const hdr = "Strategy".padEnd(30) + "Trd".padStart(4) + "Win%".padStart(6) + "PF".padStart(6) + "Net$".padStart(10) + "MaxDD$".padStart(9) + "WrstDay$".padStart(10) + "Strk".padStart(6) + "Combine".padStart(9);
  console.log(hdr); console.log("-".repeat(hdr.length));

  const out = [];
  for (const key of TOP3) {
    const r = Lab.runSignals(bars, S[key]);
    out.push({ key, r });
    const net = r.netPts * PV, dd = r.ddPts * PV, wd = Math.abs(r.worstDayPts * PV);
    const survive = wd < DLL && dd < MLL ? "OK" : (wd >= DLL ? "DLL!" : "MLL!");
    console.log(
      Lab.NAMES[key].padEnd(30) + String(r.n).padStart(4) + (f(r.winRate) + "%").padStart(6) +
      (r.pf === Infinity ? "inf" : f(r.pf, 2)).padStart(6) +
      ((net >= 0 ? "+$" : "-$") + f(Math.abs(net))).padStart(10) +
      ("$" + f(dd)).padStart(9) + ("-$" + f(wd)).padStart(10) +
      (r.maxLossStreak + "L").padStart(6) + survive.padStart(9)
    );
  }

  console.log(`\n13d -> 58d hold-up (did the edge survive out of sample?):`);
  for (const { key, r } of out) {
    const b = BASE13[key];
    const held = r.pf >= 1.2 && r.netPts > 0;
    console.log(`  ${Lab.NAMES[key].replace(/^\d+\.\s*/, "").padEnd(26)} PF ${f(b.pf, 2)} -> ${f(r.pf, 2)}   win ${f(b.winRate)}% -> ${f(r.winRate)}%   ${held ? "EDGE HOLDS" : "edge faded"}`);
  }
  console.log(`\nNote: 58d is the real test vs the 13d single-regime fingerprint. Survivability at 5 MNQ still hinges on a daily-loss lockout.`);
})().catch((e) => { console.error("validate58 error:", e.message); process.exit(1); });
