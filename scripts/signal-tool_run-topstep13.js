// run-topstep13.js — re-run the top-10 strat-gen configs (same ones from run90)
// on TopStep's most recent 13 trading days (live ProjectX feed, sim sub), using
// strat-gen's exact evalStrategy (fixed 5 MNQ, no risk overlay) — apples-to-apples
// with the 90-day table. Full indicator warmup from earlier bars.
"use strict";
const fs = require("fs");
const path = require("path");
const Lab = require("./lab-new4.js");
const G = require("./strat-gen.js");
const PX = require("./projectx.js");
const dol = x => (x >= 0 ? "+$" : "-$") + Math.abs(Math.round(x)).toLocaleString();

const byKey = new Map();
for (const [key, name, cat, fn] of G.ENTRIES) for (const ex of G.EXITS) byKey.set(`${key}|${ex.tag}`, { name: `${name} · ${ex.tag}`, cat, fn, ex });
// pick the 10 best DISTINCT entry edges (dedupe by entry key, keep each edge's
// best-ranked config) — actual different strategies, not RR variants of a few.
const ranked = JSON.parse(fs.readFileSync(path.join(__dirname, "logs", "strat150-results.json"), "utf8"));
const family = key => key.split("|")[0].match(/^[a-z]+/)[0]; // collapse fvg_w6_g02/fvg_trend -> "fvg", pin_2x/pin_ema50 -> "pin", etc.
const seen = new Set(), top = [];
for (const r of ranked) { const fam = family(r.key); if (seen.has(fam)) continue; seen.add(fam); top.push(r); if (top.length === 10) break; }

(async () => {
  const bars = (await PX.fetchBars({ unitNumber: 5, lookbackDays: 25, contract: "MNQ", live: false }))
    .filter(b => b && isFinite(b.c)).sort((a, b) => a.t - b.t);
  const rthDays = [...new Set(bars.filter(b => { const e = Lab.etParts(b.t); return e.day !== 0 && e.day !== 6 && e.mins >= 570 && e.mins < 960; }).map(b => Lab.dayKeyOf(b.t)))];
  const last13 = rthDays.slice(-13);
  const cutoffT = bars.find(b => Lab.dayKeyOf(b.t) === last13[0]).t;
  const span = [cutoffT, bars[bars.length - 1].t].map(s => new Date(s * 1000).toISOString().slice(0, 10));
  console.log(`TopStep last ${last13.length} trading days: ${span.join(" -> ")}  (${bars.length} bars w/ warmup)\n`);

  const C = G.buildContext(bars);
  console.log("orig#  strategy".padEnd(46) + "cat".padEnd(7) + "Trd  Win    PF      Net      MaxDD   WorstDay  Feas");
  top.forEach((r, idx) => {
    const s = byKey.get(r.key);
    const gated = (C2, i) => (bars[i].t >= cutoffT ? s.fn(C2, i) : 0);
    const R = G.evalStrategy(bars, C, gated, s.ex);
    console.log(String(r.rank).padStart(4) + "  " + s.name.slice(0, 38).padEnd(40) + s.cat.padEnd(7) +
      String(R.n).padStart(3) + " " + (R.win + "%").padStart(6) + " " + String(R.pf).padStart(5) +
      " " + dol(R.net$).padStart(8) + " " + ("-$" + R.dd$).padStart(8) + " " + ("-$" + R.wd$).padStart(8) + "   " + (R.feasible ? "ok" : "DD!"));
  });
})().catch(e => console.log("ERR", e.message, e.stack));
