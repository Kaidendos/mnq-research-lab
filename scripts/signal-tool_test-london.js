// test-london.js — does the Engulf@BB edge exist in the LONDON session vs US RTH?
// Same signal, same fixed exit (1xATR/3xATR, $400 cap); only the trading window changes.
// London ≈ 08:00–16:30 London time = 03:00–11:30 ET (summer). NOTE: NQ liquidity is thinner
// in London hours, so real slippage would likely be worse than the fixed 2-tick modeled here.
"use strict";
const fs = require("fs"), path = require("path");
require("./public/indicators.js");
const I = globalThis.Indicators;
const { testCombine, monteCarlo, signal } = require("./best-strategy.js");

const PV=2, MAXC=5, DLL=1000, MLL=2000, TICK=0.25, FEE=0.37, SLIP=2*TICK;
const STOP_MULT=1.0, TGT_MULT=3.0, RISK_CAP=400, MAX_TR=3, DAY_STOP=-700;

function etParts(u){
  const ms0=u*1000, y=new Date(ms0).getUTCFullYear();
  const ms=new Date(Date.UTC(y,2,1)); ms.setUTCDate(1+((7-ms.getUTCDay())%7)+7);
  const ns=new Date(Date.UTC(y,10,1)); ns.setUTCDate(1+((7-ns.getUTCDay())%7));
  const off=(ms0>=ms.getTime()&&ms0<ns.getTime())?-240:-300;
  const et=new Date(ms0+off*60000);
  return{dow:et.getUTCDay(),mins:et.getUTCHours()*60+et.getUTCMinutes(),
    dk:et.getUTCFullYear()+"-"+String(et.getUTCMonth()+1).padStart(2,"0")+"-"+String(et.getUTCDate()).padStart(2,"0")};
}

// w = {sessS,sessE,entS,entE} in ET minutes
function run(bars, w){
  bars=bars.filter(b=>b&&isFinite(b.c)).sort((a,b)=>a.t-b.t);
  const n=bars.length;
  const o=bars.map(b=>b.o),h=bars.map(b=>b.h),l=bars.map(b=>b.l),c=bars.map(b=>b.c);
  const dk=new Array(n),inS=new Array(n),dm=new Array(n);
  for(let i=0;i<n;i++){const p=etParts(bars[i].t);dk[i]=p.dk;dm[i]=p.mins;inS[i]=p.dow>=1&&p.dow<=5&&p.mins>=w.sessS&&p.mins<w.sessE;}
  const sma=I.sma(c,20),std=I.stdev(c,20),atr=I.atr(h,l,c,14);
  const bbU=sma.map((v,i)=>v==null?null:v+2*std[i]), bbL=sma.map((v,i)=>v==null?null:v-2*std[i]);
  let eq=0,pk=0,mdd=0,wins=0,gW=0,gL=0; const trades=[],byd=new Map();
  let pos=null,ds={k:null,pnl:0,tr:0},i=210;
  while(i<n){
    const b=bars[i],day=dk[i],inSess=inS[i];
    if(day!==ds.k)ds={k:day,pnl:0,tr:0};
    if(pos){
      const lng=pos.dir===1; let px=null;
      if(day!==pos.day||!inSess)                 px=lng?bars[i-1].c-SLIP:bars[i-1].c+SLIP;
      else if(lng?b.l<=pos.stop:b.h>=pos.stop)   px=lng?pos.stop-SLIP:pos.stop+SLIP;
      else if(lng?b.h>=pos.target:b.l<=pos.target)px=pos.target;
      if(px!=null){const pts=lng?px-pos.entry:pos.entry-px;const pnl=pts*pos.size*PV-2*pos.size*FEE;
        eq+=pnl;pk=Math.max(pk,eq);mdd=Math.max(mdd,pk-eq);ds.pnl+=pnl;byd.set(day,(byd.get(day)||0)+pnl);
        if(pnl>0){wins++;gW+=pnl;}else{gL+=Math.abs(pnl);}trades.push({pnl,day,dir:pos.dir});pos=null;i++;continue;}
    }
    if(!pos&&inSess&&dm[i]>=w.entS&&dm[i]<w.entE&&ds.pnl>DAY_STOP&&ds.tr<MAX_TR){
      const a=atr[i];let d=0; if(a!=null&&a>0)d=signal(o,h,l,c,bbU,bbL,atr,i);
      if(d){const sp=STOP_MULT*a,sz=Math.max(1,Math.min(MAXC,Math.floor(RISK_CAP/(sp*PV))));
        const fill=d===1?c[i]+SLIP:c[i]-SLIP;
        pos={dir:d,entry:fill,size:sz,day,stop:d===1?fill-sp:fill+sp,target:d===1?fill+TGT_MULT*a:fill-TGT_MULT*a};ds.tr++;}
    }
    i++;
  }
  const wd=byd.size?[...byd.values()]:[0]; const worst=-Math.min(0,...wd);
  return{net$:Math.round(eq),maxDD$:Math.round(mdd),n:trades.length,
    win:trades.length?+(wins/trades.length*100).toFixed(1):0,pf:gL>0?+(gW/gL).toFixed(2):(gW>0?99:0),
    worst$:Math.round(worst),feasible:mdd<MLL&&worst<DLL,trades};
}

const bars=JSON.parse(fs.readFileSync(path.join(__dirname,"data","nq-5m.json"),"utf8"));
const sessions=[
  ["US RTH (baseline)", {sessS:570,sessE:960,entS:600,entE:930}],   // 9:30-16:00, entries 10:00-15:30
  ["London full",       {sessS:180,sessE:690,entS:210,entE:660}],   // 03:00-11:30, entries 03:30-11:00
  ["London core AM",    {sessS:180,sessE:690,entS:210,entE:540}],   // entries 03:30-09:00
  ["London/US overlap", {sessS:480,sessE:720,entS:510,entE:690}],   // entries 08:30-11:30
];
console.log("Engulf@BB by session  (data/nq-5m.json, 2026-04-09→06-18, fixed exit, 2-tick slip modeled)\n");
console.log("session             net$     PF    win%   trades  maxDD$  worstDay$  feasible  Combine        MC%");
for(const [name,w] of sessions){
  const r=run(bars,w); const cp=testCombine(r.trades); const mc=monteCarlo(r.trades,3000);
  console.log(name.padEnd(18)+("$"+r.net$).padStart(8)+"  "+String(r.pf).padStart(4)+"  "+(r.win+"%").padStart(5)+"  "+
    String(r.n).padStart(6)+"  "+("$"+r.maxDD$).padStart(7)+"  "+("$"+r.worst$).padStart(8)+"   "+
    (r.feasible?"YES":"no ").padStart(7)+"  "+(cp.passed?`PASS(${cp.days}d)`:`FAIL:${cp.why}`).padEnd(13)+"  "+(mc.pct+"%").padStart(5));
}
console.log("\nCaveat: London NQ is thinner than US RTH — real slippage/fills would likely be worse than modeled.");
