// ╔══════════════════════════════════════════════════════════════════════════╗
// ║          BEST STRATEGY — NQ/MNQ 5-min Futures                          ║
// ║          L1: Engulfing Bar at Bollinger Band (10am+ filter)             ║
// ╠══════════════════════════════════════════════════════════════════════════╣
// ║ BACKTEST RESULTS (50 RTH days, Apr 9 – Jun 18 2026, vs K8 champion)    ║
// ║   Full period net:    +$12,307   (K8 was +$9,300)                      ║
// ║   Max drawdown:       -$1,524    (K8 was -$1,887)                      ║
// ║   Win rate:           43.8%                                             ║
// ║   Profit factor:      1.80                                              ║
// ║   Combine PASS:       6 trading days  (K8 was 9 days)                  ║
// ║   Monte Carlo:        87.5% of random orderings still PASS             ║
// ║   Under-13 days:      62% of passing MC runs hit target in ≤13 days   ║
// ╠══════════════════════════════════════════════════════════════════════════╣
// ║ TOPSTEP $50K COMBINE RULES                                              ║
// ║   Profit target:  +$3,000   Max trailing DD: -$2,000                   ║
// ║   Daily loss limit: -$1,000                                             ║
// ╠══════════════════════════════════════════════════════════════════════════╣
// ║ TRADE RULES                                                             ║
// ║   Instrument:   MNQ (Micro NQ Futures), $2/point/contract              ║
// ║   Timeframe:    5-minute bars, RTH only (9:30am–4:00pm ET)             ║
// ║   Time filter:  No trades before 10:00am ET                            ║
// ║   Time cutoff:  No new entries after 3:30pm ET                         ║
// ║   Max trades/day: 3                                                     ║
// ║   Daily stop:   -$700 (stop trading for the day)                       ║
// ║   Risk cap:     $400 per trade (drives position size)                  ║
// ║   Stop loss:    1.0 × ATR(14) from entry                               ║
// ║   Profit target: 3.0 × ATR(14) from entry  [3:1 R/R]                  ║
// ║   Size formula: floor($400 / (stop_pts × $2)), capped at 5 contracts   ║
// ║   Costs:        $0.37/side/contract + 2-tick slippage each way         ║
// ╠══════════════════════════════════════════════════════════════════════════╣
// ║ THE PATTERN: Body-Engulfing Bar at Bollinger Band                       ║
// ║                                                                         ║
// ║  LONG (bullish engulf at lower BB):                                     ║
// ║   1. Prior bar is RED (bearish)                                         ║
// ║   2. Current bar is GREEN (bullish)                                     ║
// ║   3. Current body fully contains prior body (open-to-close range)      ║
// ║   4. Current body size ≥ 0.4 × ATR (meaningful bar)                   ║
// ║   5. Bar low ≤ Lower BB + 0.3×ATR  (touching the band)                ║
// ║   6. Bar close > Lower BB  (snapped back inside)                       ║
// ║   → Enter LONG at close, stop = entry - ATR, target = entry + 3×ATR   ║
// ║                                                                         ║
// ║  SHORT (bearish engulf at upper BB): exact mirror                       ║
// ╠══════════════════════════════════════════════════════════════════════════╣
// ║ WHY IT WORKS                                                            ║
// ║  • BB touch = price 2 std devs from mean → statistically stretched     ║
// ║  • Engulfing bar = larger opposing bar absorbs the prior move → real    ║
// ║    buying/selling pressure has entered                                  ║
// ║  • 10am+ filter = skip noisy open auction where gaps/news dominate     ║
// ║  • 3:1 R/R = profitable even at 36% win rate                           ║
// ╚══════════════════════════════════════════════════════════════════════════╝
"use strict";
const fs = require("fs"), path = require("path");
require("./public/indicators.js");
const I = globalThis.Indicators;

// ── Constants ──────────────────────────────────────────────────────────────
const PV = 2, MAXC = 5, DLL = 1000, MLL = 2000, TARGET = 3000;
const TICK = 0.25, FEE = 0.37, SLIP = 2 * TICK;
const RTH_S = 570, RTH_E = 960;
// Strategy params (grid-optimized)
const STOP_MULT = 1.0, TGT_MULT = 3.0, RISK_CAP = 400;
const MAX_TR = 3, DAY_STOP = -700;
const TIME_FILTER = 600; // 10:00am ET
const TIME_CUTOFF = 930; // 3:30pm ET

// ── ET timezone helper ─────────────────────────────────────────────────────
function etParts(unixSec) {
  const u = unixSec * 1000, d = new Date(u), y = d.getUTCFullYear();
  const ms = new Date(Date.UTC(y,2,1)); ms.setUTCDate(1+((7-ms.getUTCDay())%7)+7);
  const ns = new Date(Date.UTC(y,10,1)); ns.setUTCDate(1+((7-ns.getUTCDay())%7));
  const off = (u >= ms.getTime() && u < ns.getTime()) ? -240 : -300;
  const et = new Date(u + off * 60000);
  return {
    dow: et.getUTCDay(),
    mins: et.getUTCHours() * 60 + et.getUTCMinutes(),
    dk: et.getUTCFullYear() + "-" + String(et.getUTCMonth()+1).padStart(2,"0") + "-" + String(et.getUTCDate()).padStart(2,"0"),
  };
}

// ── Signal: Engulfing bar at Bollinger Band ────────────────────────────────
function signal(o, h, l, c, bbU, bbL, atr, i) {
  if (i < 1 || bbU[i] == null || atr[i] == null) return 0;
  const pH = Math.max(o[i-1], c[i-1]), pL = Math.min(o[i-1], c[i-1]);
  const cH = Math.max(o[i],   c[i]),   cL = Math.min(o[i],   c[i]);
  if (cH - cL < 0.4 * atr[i]) return 0; // bar too small
  const engulfs = cL <= pL && cH >= pH;
  // Bullish engulf at lower BB
  if (c[i-1] < o[i-1] && c[i] > o[i] && engulfs &&
      l[i] <= bbL[i] + 0.3 * atr[i] && c[i] > bbL[i]) return 1;
  // Bearish engulf at upper BB
  if (c[i-1] > o[i-1] && c[i] < o[i] && engulfs &&
      h[i] >= bbU[i] - 0.3 * atr[i] && c[i] < bbU[i]) return -1;
  return 0;
}

// ── Backtest (proven while-loop pattern) ───────────────────────────────────
function runBacktest(bars) {
  bars = bars.filter(b => b && isFinite(b.c)).sort((a,b) => a.t - b.t);
  const n = bars.length;
  const o = bars.map(b=>b.o), h = bars.map(b=>b.h), l = bars.map(b=>b.l), c = bars.map(b=>b.c);

  // Precompute ET arrays (fast, no locale)
  const dk  = new Array(n), rth = new Array(n), dm = new Array(n);
  for (let i = 0; i < n; i++) {
    const p = etParts(bars[i].t);
    dk[i]  = p.dk;
    dm[i]  = p.mins;
    rth[i] = p.dow >= 1 && p.dow <= 5 && p.mins >= RTH_S && p.mins < RTH_E;
  }

  // Indicators
  const sma20 = I.sma(c, 20), std20 = I.stdev(c, 20), atr = I.atr(h, l, c, 14);
  const bbU = sma20.map((v,i) => v == null ? null : v + 2*std20[i]);
  const bbL = sma20.map((v,i) => v == null ? null : v - 2*std20[i]);

  // State
  let eq = 0, pk = 0, mdd = 0, wins = 0, gW = 0, gL = 0;
  const trades = [], byd = new Map();
  let pos = null, ds = { k: null, pnl: 0, tr: 0 };
  let i = 210;

  while (i < n) {
    const b = bars[i], day = dk[i], inRTH = rth[i];
    if (day !== ds.k) ds = { k: day, pnl: 0, tr: 0 };

    // ── Manage open position ──
    if (pos) {
      const lng = pos.dir === 1; let px = null;
      if (day !== pos.day || !inRTH)     px = lng ? bars[i-1].c - SLIP : bars[i-1].c + SLIP;
      else if (lng ? b.l <= pos.stop  : b.h >= pos.stop)   px = lng ? pos.stop   - SLIP : pos.stop   + SLIP;
      else if (lng ? b.h >= pos.target : b.l <= pos.target) px = pos.target;
      if (px != null) {
        const pts = lng ? px - pos.entry : pos.entry - px;
        const pnl = pts * pos.size * PV - 2 * pos.size * FEE;
        eq += pnl; pk = Math.max(pk, eq); mdd = Math.max(mdd, pk - eq);
        ds.pnl += pnl; byd.set(day, (byd.get(day)||0) + pnl);
        if (pnl > 0) { wins++; gW += pnl; } else { gL += Math.abs(pnl); }
        trades.push({ pnl, day, dir: pos.dir, pts });
        pos = null; i++; continue;
      }
    }

    // ── Check for new entry ──
    if (!pos && inRTH
        && dm[i] >= TIME_FILTER   // no trades before 10am
        && dm[i] < TIME_CUTOFF    // no entries after 3:30pm
        && ds.pnl > DAY_STOP      // day not stopped out
        && ds.tr < MAX_TR) {
      const a = atr[i]; let d = 0;
      if (a != null && a > 0) d = signal(o, h, l, c, bbU, bbL, atr, i);
      if (d) {
        const sp = STOP_MULT * a, sz = Math.max(1, Math.min(MAXC, Math.floor(RISK_CAP / (sp * PV))));
        const fill = d === 1 ? c[i] + SLIP : c[i] - SLIP;
        pos = { dir: d, entry: fill, size: sz, day,
                stop:   d === 1 ? fill - sp        : fill + sp,
                target: d === 1 ? fill + TGT_MULT*a : fill - TGT_MULT*a };
        ds.tr++;
      }
    }

    i++;
  }

  const wdV = byd.size ? [...byd.values()] : [0];
  return {
    net$: Math.round(eq), maxDD$: Math.round(mdd),
    n: trades.length, win: trades.length ? +(wins/trades.length*100).toFixed(1) : 0,
    pf: gL > 0 ? +(gW/gL).toFixed(2) : (gW > 0 ? 99 : 0),
    worstDay$: Math.round(-Math.min(0, ...wdV)),
    feasible: mdd < MLL && (-Math.min(0,...wdV)) < DLL,
    trades, byd,
  };
}

// ── Combine pass test ───────────────────────────────────────────────────────
function testCombine(trades) {
  let cum = 0, pk = 0; const bd = new Map(), days = new Set();
  for (const t of trades) {
    days.add(t.day); cum += t.pnl; pk = Math.max(pk, cum);
    bd.set(t.day, (bd.get(t.day)||0) + t.pnl);
    if (pk - cum >= MLL) return { passed: false, why: "trailing DD",   days: days.size };
    if (bd.get(t.day) <= -DLL) return { passed: false, why: "daily loss", days: days.size };
    if (cum >= TARGET)  return { passed: true,  why: "target hit",     days: days.size };
  }
  return { passed: false, why: "target not reached", days: days.size };
}

// ── Monte Carlo ─────────────────────────────────────────────────────────────
function monteCarlo(trades, iters = 2000) {
  if (!trades.length) return { pct: 0, medDays: null, under13: 0 };
  const p = trades.map(t=>t.pnl), d = trades.map(t=>t.day);
  let pass = 0, u13 = 0; const passDays = [];
  for (let it = 0; it < iters; it++) {
    const idx = Array.from({length:p.length},(_,k)=>k);
    for (let k=idx.length-1;k>0;k--){const j=(Math.random()*(k+1))|0;[idx[k],idx[j]]=[idx[j],idx[k]];}
    let cum=0,pk=0,ok=false,dead=false; const ds=new Set();
    for (const ii of idx) {
      ds.add(d[ii]); cum+=p[ii]; pk=Math.max(pk,cum);
      if (pk-cum>=MLL){dead=true;break;} if(cum>=TARGET){ok=true;break;}
    }
    if (ok && !dead) { pass++; passDays.push(ds.size); if(ds.size<=13)u13++; }
  }
  passDays.sort((a,b)=>a-b);
  return { pct: +(pass/iters*100).toFixed(1),
    medDays: passDays.length ? passDays[Math.floor(passDays.length/2)] : null,
    under13: pass > 0 ? +(u13/pass*100).toFixed(0) : 0 };
}

// ── Run ─────────────────────────────────────────────────────────────────────
if (require.main === module) {
  const bars = JSON.parse(fs.readFileSync(path.join(__dirname,"data","nq-5m.json"),"utf8"));
  const r = runBacktest(bars);
  const cp = testCombine(r.trades);
  const mc = monteCarlo(r.trades);

  const dol = x => (x>=0?"+$":"-$") + Math.abs(x).toLocaleString();
  console.log("╔══════════════════════════════════════════════════════╗");
  console.log("║  BEST STRATEGY: Engulfing@BB (10am+ filter)         ║");
  console.log("╠══════════════════════════════════════════════════════╣");
  console.log("║  Full P&L:      " + dol(r.net$).padEnd(36) + "║");
  console.log("║  Max DD:        -$" + String(r.maxDD$).padEnd(34) + "║");
  console.log("║  Trades:        " + String(r.n).padEnd(36) + "║");
  console.log("║  Win rate:      " + String(r.win+"%").padEnd(36) + "║");
  console.log("║  Profit factor: " + String(r.pf).padEnd(36) + "║");
  console.log("║  Worst day:     -$" + String(r.worstDay$).padEnd(34) + "║");
  console.log("║  Feasible:      " + String(r.feasible ? "YES ✓" : "NO ✗").padEnd(36) + "║");
  console.log("╠══════════════════════════════════════════════════════╣");
  console.log("║  COMBINE: " + String(cp.passed ? "PASS in "+cp.days+" trading days" : "FAIL — "+cp.why).padEnd(43) + "║");
  console.log("║  MC pass rate:  " + String(mc.pct+"%").padEnd(36) + "║");
  console.log("║  MC median:     " + String((mc.medDays||"--")+"d to pass").padEnd(36) + "║");
  console.log("║  Under-13 days: " + String(mc.under13+"%").padEnd(36) + "║");
  console.log("╚══════════════════════════════════════════════════════╝");

  console.log("\nDay-by-day (full period):");
  let cum = 0;
  for (const [day, pnl] of [...r.byd.entries()].sort((a,b)=>a[0].localeCompare(b[0]))) {
    cum += pnl; console.log("  "+day+"  "+dol(Math.round(pnl)).padStart(8)+"  (running: "+dol(Math.round(cum))+")");
  }
}

module.exports = { runBacktest, testCombine, monteCarlo, signal };
