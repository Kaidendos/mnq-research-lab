// =============================================================
//  test-trailing.js — does a trailing/breakeven stop actually HELP Engulf@BB?
//  Same data + same entries as best-strategy.js; only the STOP management changes.
//  Modes:
//    fixed     baseline: 1xATR stop, 3xATR target, no trailing (the deployed strat)
//    be1       move stop to breakeven once trade is +1xATR in favor
//    trail2    after +1xATR, trail stop at peak - 2xATR
//    trail1p5  after +1xATR, trail stop at peak - 1.5xATR
//    trail1    after +1xATR, trail stop at peak - 1xATR (tightest)
//  All keep the 3xATR target as the upside cap (so winners can still run full).
// =============================================================
"use strict";
const fs = require("fs"), path = require("path");
require("./public/indicators.js");
const I = globalThis.Indicators;
const { testCombine, monteCarlo, signal } = require("./best-strategy.js");

const PV = 2, MAXC = 5, DLL = 1000, MLL = 2000;
const TICK = 0.25, FEE = 0.37, SLIP = 2 * TICK;
const RTH_S = 570, RTH_E = 960;
const STOP_MULT = 1.0, TGT_MULT = 3.0, RISK_CAP = 400;
const MAX_TR = 3, DAY_STOP = -700;
const TIME_FILTER = 600, TIME_CUTOFF = 930;

function etParts(u) {
  const ms0 = u * 1000, y = new Date(ms0).getUTCFullYear();
  const ms = new Date(Date.UTC(y,2,1)); ms.setUTCDate(1+((7-ms.getUTCDay())%7)+7);
  const ns = new Date(Date.UTC(y,10,1)); ns.setUTCDate(1+((7-ns.getUTCDay())%7));
  const off = (ms0 >= ms.getTime() && ms0 < ns.getTime()) ? -240 : -300;
  const et = new Date(ms0 + off * 60000);
  return { dow: et.getUTCDay(), mins: et.getUTCHours()*60+et.getUTCMinutes(),
    dk: et.getUTCFullYear()+"-"+String(et.getUTCMonth()+1).padStart(2,"0")+"-"+String(et.getUTCDate()).padStart(2,"0") };
}

// raise (long) / lower (short) the stop per mode, using favorable excursion
function trailStop(pos, b, mode) {
  const lng = pos.dir === 1, a = pos.atr;
  if (lng) {
    pos.peak = Math.max(pos.peak, b.h);
    const gain = pos.peak - pos.entry;
    if (gain < 1 * a) return;
    if (mode === "be1") pos.stop = Math.max(pos.stop, pos.entry);
    else if (mode === "trail2")   pos.stop = Math.max(pos.stop, pos.peak - 2.0 * a);
    else if (mode === "trail1p5") pos.stop = Math.max(pos.stop, pos.peak - 1.5 * a);
    else if (mode === "trail1")   pos.stop = Math.max(pos.stop, pos.peak - 1.0 * a);
  } else {
    pos.peak = Math.min(pos.peak, b.l);
    const gain = pos.entry - pos.peak;
    if (gain < 1 * a) return;
    if (mode === "be1") pos.stop = Math.min(pos.stop, pos.entry);
    else if (mode === "trail2")   pos.stop = Math.min(pos.stop, pos.peak + 2.0 * a);
    else if (mode === "trail1p5") pos.stop = Math.min(pos.stop, pos.peak + 1.5 * a);
    else if (mode === "trail1")   pos.stop = Math.min(pos.stop, pos.peak + 1.0 * a);
  }
}

function run(bars, mode) {
  bars = bars.filter(b => b && isFinite(b.c)).sort((a,b) => a.t - b.t);
  const n = bars.length;
  const o = bars.map(b=>b.o), h = bars.map(b=>b.h), l = bars.map(b=>b.l), c = bars.map(b=>b.c);
  const dk = new Array(n), rth = new Array(n), dm = new Array(n);
  for (let i = 0; i < n; i++) { const p = etParts(bars[i].t); dk[i]=p.dk; dm[i]=p.mins; rth[i]=p.dow>=1&&p.dow<=5&&p.mins>=RTH_S&&p.mins<RTH_E; }
  const sma20 = I.sma(c,20), std20 = I.stdev(c,20), atr = I.atr(h,l,c,14);
  const bbU = sma20.map((v,i)=>v==null?null:v+2*std20[i]);
  const bbL = sma20.map((v,i)=>v==null?null:v-2*std20[i]);

  let eq=0, pk=0, mdd=0, wins=0, gW=0, gL=0;
  const trades=[], byd=new Map();
  let pos=null, ds={k:null,pnl:0,tr:0}, i=210;

  while (i < n) {
    const b = bars[i], day = dk[i], inRTH = rth[i];
    if (day !== ds.k) ds = { k: day, pnl: 0, tr: 0 };
    if (pos) {
      const lng = pos.dir === 1; let px = null;
      if (day !== pos.day || !inRTH)                          px = lng ? bars[i-1].c-SLIP : bars[i-1].c+SLIP;
      else if (lng ? b.l <= pos.stop   : b.h >= pos.stop)     px = lng ? pos.stop-SLIP : pos.stop+SLIP;
      else if (lng ? b.h >= pos.target : b.l <= pos.target)   px = pos.target;
      if (px != null) {
        const pts = lng ? px - pos.entry : pos.entry - px;
        const pnl = pts * pos.size * PV - 2 * pos.size * FEE;
        eq += pnl; pk = Math.max(pk, eq); mdd = Math.max(mdd, pk - eq);
        ds.pnl += pnl; byd.set(day, (byd.get(day)||0) + pnl);
        if (pnl > 0) { wins++; gW += pnl; } else { gL += Math.abs(pnl); }
        trades.push({ pnl, day, dir: pos.dir }); pos = null; i++; continue;
      }
      trailStop(pos, b, mode);
    }
    if (!pos && inRTH && dm[i] >= TIME_FILTER && dm[i] < TIME_CUTOFF && ds.pnl > DAY_STOP && ds.tr < MAX_TR) {
      const a = atr[i]; let d = 0;
      if (a != null && a > 0) d = signal(o,h,l,c,bbU,bbL,atr,i);
      if (d) {
        const sp = STOP_MULT*a, sz = Math.max(1, Math.min(MAXC, Math.floor(RISK_CAP/(sp*PV))));
        const fill = d===1 ? c[i]+SLIP : c[i]-SLIP;
        pos = { dir:d, entry:fill, size:sz, day, atr:a, peak:fill,
                stop: d===1?fill-sp:fill+sp, target: d===1?fill+TGT_MULT*a:fill-TGT_MULT*a };
        ds.tr++;
      }
    }
    i++;
  }
  const wd = byd.size ? [...byd.values()] : [0];
  const worst = -Math.min(0, ...wd);
  return { net$: Math.round(eq), maxDD$: Math.round(mdd), n: trades.length,
    win: trades.length ? +(wins/trades.length*100).toFixed(1) : 0,
    pf: gL>0 ? +(gW/gL).toFixed(2) : (gW>0?99:0),
    worst$: Math.round(worst), feasible: mdd < MLL && worst < DLL, trades };
}

const bars = JSON.parse(fs.readFileSync(path.join(__dirname,"data","nq-5m.json"),"utf8"));
const modes = ["fixed","be1","trail2","trail1p5","trail1"];
console.log("Engulf@BB exit-management sweep  (data/nq-5m.json, same entries, costs incl.)\n");
console.log("mode      net$     PF    win%   trades  maxDD$  worstDay$  feasible  Combine        MC%");
for (const m of modes) {
  const r = run(bars, m);
  const cp = testCombine(r.trades);
  const mc = monteCarlo(r.trades, 3000);
  const combine = cp.passed ? `PASS(${cp.days}d)` : `FAIL:${cp.why}`;
  console.log(
    m.padEnd(9) +
    ("$"+r.net$).padStart(8) + "  " +
    String(r.pf).padStart(4) + "  " +
    (r.win+"%").padStart(5) + "  " +
    String(r.n).padStart(6) + "  " +
    ("$"+r.maxDD$).padStart(7) + "  " +
    ("$"+r.worst$).padStart(8) + "   " +
    (r.feasible?"YES":"no ").padStart(7) + "  " +
    combine.padEnd(13) + "  " +
    (mc.pct+"%").padStart(5)
  );
}
console.log("\nbaseline = 'fixed' (currently deployed). A variant only wins if it beats fixed on net AND stays feasible.");
