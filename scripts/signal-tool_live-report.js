// =============================================================
//  live-report.js — Engulf@BB LIVE forward-test scorecard.
//  Reads logs/live-engulfing.jsonl (the bot's audit log) and scores the real
//  armed trades against the backtest expectancy, plus Combine-feasibility.
//    node live-report.js            full scorecard (armed/live trades)
//    node live-report.js --paper    include dry-run/paper trades too
//  Writes logs/forward-test-report.md and prints to console.
// =============================================================
"use strict";
const fs = require("fs"), path = require("path");
const LOG = path.join(__dirname, "logs", "live-engulfing.jsonl");
const OUT = path.join(__dirname, "logs", "forward-test-report.md");

// ── backtest benchmarks (from best-strategy.js header) ──
const BT = { win: 43.8, pf: 1.80, target: 3000, mll: 2000, dll: 1000 };
const includePaper = process.argv.includes("--paper");

// ET day key with correct DST (2nd-Sun-Mar .. 1st-Sun-Nov), mirrors the bot.
function etDay(iso) {
  const u = new Date(iso).getTime(), y = new Date(u).getUTCFullYear();
  const ms = new Date(Date.UTC(y, 2, 1)); ms.setUTCDate(1 + ((7 - ms.getUTCDay()) % 7) + 7);
  const ns = new Date(Date.UTC(y, 10, 1)); ns.setUTCDate(1 + ((7 - ns.getUTCDay()) % 7));
  const off = (u >= ms.getTime() && u < ns.getTime()) ? -240 : -300;
  const d = new Date(u + off * 60000);
  return d.getUTCFullYear() + "-" + String(d.getUTCMonth() + 1).padStart(2, "0") + "-" + String(d.getUTCDate()).padStart(2, "0");
}
const money = x => (x >= 0 ? "+$" : "-$") + Math.abs(x).toLocaleString(undefined, { maximumFractionDigits: 0 });

function load() {
  let lines = [];
  try { lines = fs.readFileSync(LOG, "utf8").split("\n").filter(Boolean); } catch { return []; }
  const exits = [];
  for (const ln of lines) {
    let r; try { r = JSON.parse(ln); } catch { continue; }
    if (r.type !== "exit") continue;
    if (!includePaper && r.live !== true) continue;
    exits.push(r);
  }
  return exits.sort((a, b) => new Date(a.ts) - new Date(b.ts));
}

function build() {
  const tr = load();
  const n = tr.length;
  if (!n) return "No closed trades logged yet.\n";

  const wins = tr.filter(t => t.pnl > 0), losses = tr.filter(t => t.pnl <= 0);
  const gW = wins.reduce((s, t) => s + t.pnl, 0), gL = Math.abs(losses.reduce((s, t) => s + t.pnl, 0));
  const net = gW - gL, win = +(wins.length / n * 100).toFixed(1);
  const pf = gL > 0 ? +(gW / gL).toFixed(2) : (gW > 0 ? 99 : 0);
  const avgW = wins.length ? gW / wins.length : 0, avgL = losses.length ? gL / losses.length : 0;
  const exp = net / n;

  // equity curve / drawdown / worst day / progress
  let eq = 0, pk = 0, mdd = 0; const byDay = new Map();
  for (const t of tr) {
    eq += t.pnl; pk = Math.max(pk, eq); mdd = Math.max(mdd, pk - eq);
    const k = etDay(t.ts); byDay.set(k, (byDay.get(k) || 0) + t.pnl);
  }
  const worstDay = Math.min(0, ...[...byDay.values()]);
  const byReason = tr.reduce((m, t) => (m[t.why] = (m[t.why] || 0) + 1, m), {});

  // verdict
  let verdict;
  if (n < 10) verdict = `SMALL SAMPLE — ${n} trade${n === 1 ? "" : "s"}. Need ~30+ before win%/PF mean anything. (Today is day one — noise.)`;
  else {
    const okWin = win >= BT.win - 8, okPf = pf >= 1.2;
    verdict = (okWin && okPf) ? "ON TRACK vs backtest." :
      `WATCH — win ${win}% / PF ${pf} vs backtest ${BT.win}% / ${BT.pf}. Keep sampling.`;
  }

  const dayLines = [...byDay.entries()].map(([k, v]) => {
    const dt = tr.filter(t => etDay(t.ts) === k);
    const w = dt.filter(t => t.pnl > 0).length;
    return `| ${k} | ${money(v)} | ${dt.length} | ${w}W / ${dt.length - w}L |`;
  }).join("\n");

  return `# Engulf@BB — Live Forward-Test Scorecard
_as of ${new Date().toISOString()} · account practice XXXX · ${includePaper ? "live+paper" : "live (armed) only"}_

## Results so far
| Metric | Live | Backtest |
|---|---:|---:|
| Trades | ${n} | (50-day sample) |
| Win rate | ${win}% | ${BT.win}% |
| Profit factor | ${pf} | ${BT.pf} |
| Net P&L | ${money(net)} | — |
| Avg win / Avg loss | ${money(avgW)} / ${money(avgL)} | ~3:1 R |
| Expectancy / trade | ${money(exp)} | — |
| Exits | ${Object.entries(byReason).map(([k, v]) => `${k}:${v}`).join(", ")} | — |

## Combine feasibility (chronological)
- Progress to **+${BT.target.toLocaleString()}** target: **${money(eq)}**
- Max drawdown so far: **${money(-mdd)}**  (wall: −$${BT.mll.toLocaleString()})
- Worst day so far: **${money(worstDay)}**  (limit: −$${BT.dll.toLocaleString()})

## Verdict
${verdict}

## By day
| Day (ET) | P&L | Trades | W/L |
|---|---:|---:|---|
${dayLines}
`;
}

const report = build();
try { fs.writeFileSync(OUT, report); } catch {}
console.log(report);
