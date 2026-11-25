// run90.js — take the top-N strategies from strat-gen and run them on the
// full ~90-day MNQ 5m chart (third, larger out-of-sample). Reuses the EXACT
// entry/exit/eval code from strat-gen.js (no reimplementation).
//   node run90.js [N] ["path\to\90d.csv"]
"use strict";
const fs = require("fs");
const path = require("path");
const Lab = require("./lab-new4.js");
const G = require("./strat-gen.js");

const N = parseInt(process.argv[2] || "10", 10);
const CSV_90 = process.argv[3] || "C:\\Users\\kaide\\Downloads\\CME_MINI_DL_MNQ1!, 5 (1).csv";
const RESULTS = path.join(__dirname, "logs", "strat150-results.json");
const OUT_MD = path.join(__dirname, "logs", "top10-90d-report.md");
const dol = x => (x >= 0 ? "+$" : "-$") + Math.abs(Math.round(x)).toLocaleString();

// rebuild the strategy lookup (key -> {fn, ex}) from strat-gen's ENTRIES x EXITS
const byKey = new Map();
for (const [key, name, cat, fn] of G.ENTRIES) for (const ex of G.EXITS) byKey.set(`${key}|${ex.tag}`, { name: `${name} · ${ex.tag}`, cat, fn, ex });

const ranked = JSON.parse(fs.readFileSync(RESULTS, "utf8"));
const top = ranked.slice(0, N);

const bars = Lab.loadCsv(CSV_90);
const days = new Set(bars.map(b => Lab.dayKeyOf(b.t))).size;
const span = [bars[0].t, bars[bars.length - 1].t].map(s => new Date(s * 1000).toISOString().slice(0, 10));
const C = G.buildContext(bars);
console.log(`90d chart: ${bars.length} bars, ${days} days, ${span.join(" -> ")}\n`);

const rows = top.map(r => {
  const s = byKey.get(r.key);
  const R = G.evalStrategy(bars, C, s.fn, s.ex);
  return { rank: r.rank, name: s.name, cat: s.cat, R, prior: r };
});

console.log("orig  strategy".padEnd(46) + "cat".padEnd(7) + "90dTrd 90dWin 90dPF   90dNet   90dDD  90dWorstDay  Feas");
for (const x of rows) {
  console.log(String(x.rank).padStart(4) + "  " + x.name.slice(0, 38).padEnd(40) + x.cat.padEnd(7) +
    String(x.R.n).padStart(5) + (x.R.win + "%").padStart(7) + String(x.R.pf).padStart(6) +
    dol(x.R.net$).padStart(10) + ("-$" + x.R.dd$).padStart(8) + ("-$" + x.R.wd$).padStart(11) +
    (x.R.feasible ? "  ok" : "  DD!"));
}

const md = [];
md.push(`# Top ${N} strategies on the ~90-day chart (${new Date().toISOString().slice(0, 10)})`);
md.push(`\nTop ${N} from \`strat150-results.json\` re-run on the full **${days}-day MNQ 5m** chart (${span.join(" → ")}) — a third, larger out-of-sample. Dollars @5 MNQ ($10/pt), gross. "Feas" = worst day < $1000 AND max drawdown < $2000 at 5 MNQ.`);
md.push(`\n| Orig# | Strategy | Cat | 90d Trd | 90d Win% | 90d PF | 90d Net | 90d MaxDD | 90d WorstDay | Feasible @5MNQ | Feasible size |`);
md.push(`|---|----------|-----|----:|----:|---:|------:|------:|------:|:--:|----:|`);
for (const x of rows) {
  const feasSz = x.R.dd$ > 0 ? Math.max(1, Math.floor(2000 / (x.R.dd$ / 5))) : 5;
  md.push(`| ${x.rank} | ${x.name} | ${x.cat} | ${x.R.n} | ${x.R.win} | ${x.R.pf} | ${dol(x.R.net$)} | -$${x.R.dd$} | -$${x.R.wd$} | ${x.R.feasible ? "yes" : "DD!"} | ≤${feasSz} MNQ |`);
}
fs.mkdirSync(path.dirname(OUT_MD), { recursive: true });
fs.writeFileSync(OUT_MD, md.join("\n") + "\n");
console.log(`\nReport -> ${OUT_MD}`);
