// =============================================================
//  test-partial.js — does PARTIAL SCALE-OUT beat the fixed exit on Engulf@BB?
//  Same data + same entries as best-strategy.js. Only the exit changes:
//    take `frac` of the position off at +`scaleR`xATR (banked), let the runner
//    ride to the 3xATR target; optionally move the runner's stop to breakeven.
//  One entry = one trade (partial P&L + runner P&L combined), so win%/PF/Combine
//  stay comparable to the baseline. Fees charged per contract per leg.
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

// cfg = null (fixed baseline) OR { frac, scaleR, moveBE }
function run(bars, cfg) {
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

  const legPnl = (lng, exitPx, entry, contracts) =>
    (lng ? exitPx - entry : entry - exitPx) * contracts * PV - 2 * FEE * contracts;

  while (i < n) {
    const b = bars[i], day = dk[i], inRTH = rth[i];
    if (day !== ds.k) ds = { k: day, pnl: 0, tr: 0 };
    if (pos) {
      const lng = pos.dir === 1;
      // 1) partial scale-out (only if configured and not yet done), BEFORE final-exit checks
      if (cfg && !pos.scaled) {
        const lvl = lng ? pos.entry + cfg.scaleR*pos.atr : pos.entry - cfg.scaleR*pos.atr;
        if (lng ? b.h >= lvl : b.l <= lvl) {
          const off = Math.min(pos.rem - 1, Math.max(1, Math.round(cfg.frac * pos.size)));
          if (off >= 1) {
            pos.realized += legPnl(lng, lvl, pos.entry, off); // take-profit fill at the level
            pos.rem -= off;
            if (cfg.moveBE) pos.stop = pos.entry;
          }
          pos.scaled = true;
        }
      }
      // 2) final exit of the remaining contracts
      let px = null;
      if (day !== pos.day || !inRTH)                        px = lng ? bars[i-1].c-SLIP : bars[i-1].c+SLIP;
      else if (lng ? b.l <= pos.stop   : b.h >= pos.stop)   px = lng ? pos.stop-SLIP : pos.stop+SLIP;
      else if (lng ? b.h >= pos.target : b.l <= pos.target) px = pos.target;
      if (px != null) {
        const total = pos.realized + legPnl(lng, px, pos.entry, pos.rem);
        eq += total; pk = Math.max(pk, eq); mdd = Math.max(mdd, pk - eq);
        ds.pnl += total; byd.set(day, (byd.get(day)||0) + total);
        if (total > 0) { wins++; gW += total; } else { gL += Math.abs(total); }
        trades.push({ pnl: total, day, dir: pos.dir }); pos = null; i++; continue;
      }
    }
    if (!pos && inRTH && dm[i] >= TIME_FILTER && dm[i] < TIME_CUTOFF && ds.pnl > DAY_STOP && ds.tr < MAX_TR) {
      const a = atr[i]; let d = 0;
      if (a != null && a > 0) d = signal(o,h,l,c,bbU,bbL,atr,i);
      if (d) {
        const sp = STOP_MULT*a, sz = Math.max(1, Math.min(MAXC, Math.floor(RISK_CAP/(sp*PV))));
        const fill = d===1 ? c[i]+SLIP : c[i]-SLIP;
        pos = { dir:d, entry:fill, size:sz, rem:sz, day, atr:a, scaled:false, realized:0,
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
const cfgs = [
  ["fixed (baseline)", null],
  ["40%@1.5R +BE",  { frac:0.4, scaleR:1.5, moveBE:true }],
  ["40%@1.5R keep", { frac:0.4, scaleR:1.5, moveBE:false }],
  ["60%@1.5R +BE",  { frac:0.6, scaleR:1.5, moveBE:true }],
  ["40%@1R +BE",    { frac:0.4, scaleR:1.0, moveBE:true }],
  ["40%@2R +BE",    { frac:0.4, scaleR:2.0, moveBE:true }],
];
console.log("Engulf@BB partial scale-out sweep  (data/nq-5m.json, same entries, costs incl.)\n");
console.log("mode              net$     PF    win%   trades  maxDD$  worstDay$  feasible  Combine        MC%");
for (const [name, cfg] of cfgs) {
  const r = run(bars, cfg);
  const cp = testCombine(r.trades);
  const mc = monteCarlo(r.trades, 3000);
  const combine = cp.passed ? `PASS(${cp.days}d)` : `FAIL:${cp.why}`;
  console.log(
    name.padEnd(16) +
    ("$"+r.net$).padStart(8) + "  " + String(r.pf).padStart(4) + "  " +
    (r.win+"%").padStart(5) + "  " + String(r.n).padStart(6) + "  " +
    ("$"+r.maxDD$).padStart(7) + "  " + ("$"+r.worst$).padStart(8) + "   " +
    (r.feasible?"YES":"no ").padStart(7) + "  " + combine.padEnd(13) + "  " + (mc.pct+"%").padStart(5) +
    "  med " + ((mc.medDays||"-")+"d").padStart(4) + "  ≤13d:" + (mc.under13+"%").padStart(4)
  );
}
console.log("\nbaseline net = $12,307 / PF 2.06 / DD $1,524. A variant wins only if net >= baseline AND feasible.");
