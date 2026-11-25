// test-london-search.js — hunt the HIGHEST WIN RATE Engulf-family strategy for LONDON hours.
// 50 entry edges (imported from strat-gen) x 8 reward:risk exits = 400 strategies, London-anchored
// context (VWAP/opening-range/session H-L rebuilt on the London session), London-gated entries.
// Ranks by win rate — but prints net$/PF/feasible alongside, because high win rate is usually a trap.
"use strict";
const fs = require("fs"), path = require("path");
require("./public/indicators.js");
const I = globalThis.Indicators;
const { ENTRIES } = require("./strat-gen.js");

// London session in ET minutes (summer): 03:00–11:30 session, entries 03:30–11:00.
const SESS_S = 180, SESS_E = 690, ENT_S = 210, ENT_E = 660;
const PV = 2, MAXC = 5, DLL = 1000, MLL = 2000, TICK = 0.25, FEE = 0.37, SLIP = 2 * TICK;
const RISK_CAP = 400, MAX_TR = 3, DAY_STOP = -700;

function ep(t) {
  const u = t * 1000, y = new Date(u).getUTCFullYear();
  const ms = new Date(Date.UTC(y, 2, 1)); ms.setUTCDate(1 + ((7 - ms.getUTCDay()) % 7) + 7);
  const ns = new Date(Date.UTC(y, 10, 1)); ns.setUTCDate(1 + ((7 - ns.getUTCDay()) % 7));
  const off = (u >= ms.getTime() && u < ns.getTime()) ? -240 : -300;
  const d = new Date(u + off * 60000);
  return { day: d.getUTCDay(), mins: d.getUTCHours() * 60 + d.getUTCMinutes(),
    k: d.getUTCFullYear() + "-" + (d.getUTCMonth() + 1) + "-" + d.getUTCDate() };
}
// helpers (verbatim from strat-gen so imported ENTRIES see identical C fields)
function priorMax(a,n){const o=Array(a.length).fill(null);for(let i=n;i<a.length;i++){let m=-Infinity;for(let k=i-n;k<i;k++)m=Math.max(m,a[k]);o[i]=m;}return o;}
function priorMin(a,n){const o=Array(a.length).fill(null);for(let i=n;i<a.length;i++){let m=Infinity;for(let k=i-n;k<i;k++)m=Math.min(m,a[k]);o[i]=m;}return o;}
function stochK(h,l,c,n){const K=Array(c.length).fill(null);for(let i=n-1;i<c.length;i++){let hh=-Infinity,ll=Infinity;for(let k=i-n+1;k<=i;k++){hh=Math.max(hh,h[k]);ll=Math.min(ll,l[k]);}K[i]=hh>ll?(c[i]-ll)/(hh-ll)*100:50;}return K;}
function cciCalc(h,l,c,n){const tp=h.map((x,i)=>(x+l[i]+c[i])/3),ma=I.sma(tp,n),o=Array(c.length).fill(null);for(let i=n-1;i<c.length;i++){let md=0;for(let k=i-n+1;k<=i;k++)md+=Math.abs(tp[k]-ma[i]);md/=n;o[i]=md===0?0:(tp[i]-ma[i])/(0.015*md);}return o;}
function lastSwing(arr,isHigh,lft,rgt){const n=arr.length,o=Array(n).fill(null);let last=null;for(let i=0;i<n;i++){const c=i-rgt;if(c>=lft){let piv=true;for(let k=1;k<=lft&&piv;k++)if(isHigh?arr[c-k]>arr[c]:arr[c-k]<arr[c])piv=false;for(let k=1;k<=rgt&&piv;k++)if(isHigh?arr[c+k]>arr[c]:arr[c+k]<arr[c])piv=false;if(piv)last=arr[c];}o[i]=last;}return o;}

function sessionStuff(bars) { // London-anchored VWAP/sigma, session H/L/open, prior-day HLC, opening-range
  const N = bars.length;
  const vwap=Array(N).fill(null),sd=Array(N).fill(null),hod=Array(N).fill(null),lod=Array(N).fill(null),dOpen=Array(N).fill(null);
  const pdH=Array(N).fill(null),pdL=Array(N).fill(null),pdC=Array(N).fill(null),orH=Array(N).fill(null),orL=Array(N).fill(null);
  const order=[],H=new Map(),L=new Map(),Cc=new Map();
  let cur=null,vN=0,vD=0,vN2=0,hi=-Infinity,lo=Infinity,op=null,lastC=null,curORh=-Infinity,curORl=Infinity;
  for(let i=0;i<N;i++){
    const p=ep(bars[i].t),b=bars[i];
    if(p.k!==cur){ if(cur!=null){H.set(cur,hi);L.set(cur,lo);Cc.set(cur,lastC);order.push(cur);} cur=p.k;vN=vD=vN2=0;hi=-Infinity;lo=Infinity;op=null;curORh=-Infinity;curORl=Infinity; }
    const inR = p.day!==0&&p.day!==6&&p.mins>=SESS_S&&p.mins<SESS_E;
    if(inR){ if(op==null)op=b.o; hi=Math.max(hi,b.h);lo=Math.min(lo,b.l);lastC=b.c;
      const hlc3=(b.h+b.l+b.c)/3,v=b.v||1; vN+=hlc3*v;vN2+=hlc3*hlc3*v;vD+=v;
      if(p.mins<SESS_S+30){curORh=Math.max(curORh,b.h);curORl=Math.min(curORl,b.l);} }
    if(vD>0){const m=vN/vD;vwap[i]=m;sd[i]=Math.sqrt(Math.max(0,vN2/vD-m*m));}
    hod[i]=hi===-Infinity?null:hi;lod[i]=lo===Infinity?null:lo;dOpen[i]=op;
    orH[i]=curORh===-Infinity?null:curORh;orL[i]=curORl===Infinity?null:curORl;
    const idx=order.length-1; if(idx>=0){pdH[i]=H.get(order[idx]);pdL[i]=L.get(order[idx]);pdC[i]=Cc.get(order[idx]);}
  }
  return {vwap,sd,hod,lod,dOpen,pdH,pdL,pdC,orH,orL};
}
function buildContext(bars){
  const o=bars.map(b=>b.o),h=bars.map(b=>b.h),l=bars.map(b=>b.l),c=bars.map(b=>b.c),v=bars.map(b=>b.v||0);
  const dmi=I.dmi(h,l,c,14,14); const {macdLine,signalLine}=I.macd(c,12,26,9);
  const dev=I.stdev(c,20),sma20=I.sma(c,20);
  const bbU=sma20.map((m,i)=>m==null||dev[i]==null?null:m+2*dev[i]),bbL=sma20.map((m,i)=>m==null||dev[i]==null?null:m-2*dev[i]);
  const pctB=c.map((x,i)=>bbU[i]==null||bbU[i]===bbL[i]?null:(x-bbL[i])/(bbU[i]-bbL[i]));
  const ss=sessionStuff(bars);
  return {o,h,l,c,v,atr:I.atr(h,l,c,14),ema9:I.ema(c,9),ema20:I.ema(c,20),ema21:I.ema(c,21),ema50:I.ema(c,50),ema200:I.ema(c,200),
    sma20,rsi2:I.rsi(c,2),rsi14:I.rsi(c,14),adx:dmi.adx,macdLine,signalLine,dev,bbU,bbL,pctB,
    K:stochK(h,l,c,14),cci:cciCalc(h,l,c,20),don20H:priorMax(h,20),don20L:priorMin(l,20),don55H:priorMax(h,55),don55L:priorMin(l,55),
    swingH:lastSwing(h,true,3,3),swingL:lastSwing(l,false,3,3),swingH2:lastSwing(h,true,2,2),swingL2:lastSwing(l,false,2,2),
    ...ss, mins:bars.map(b=>ep(b.t).mins)};
}

function sim(bars, C, fn, ex) { // ex={s,t} ATR mults; fixed bracket, London-gated, EOD flatten at SESS_E
  const n=bars.length, o=C.o,h=C.h,l=C.l,c=C.c;
  const P=bars.map(b=>ep(b.t));
  let eq=0,pk=0,mdd=0,wins=0,gW=0,gL=0; const trades=[],byd=new Map();
  let pos=null,ds={k:null,pnl:0,tr:0},i=210;
  while(i<n){
    const day=P[i].k, inSess=P[i].day>=1&&P[i].day<=5&&P[i].mins>=SESS_S&&P[i].mins<SESS_E, mins=P[i].mins;
    if(day!==ds.k)ds={k:day,pnl:0,tr:0};
    if(pos){
      const lng=pos.dir===1;let px=null;
      if(day!==pos.day||!inSess)px=lng?c[i-1]-SLIP:c[i-1]+SLIP;
      else if(lng?l[i]<=pos.stop:h[i]>=pos.stop)px=lng?pos.stop-SLIP:pos.stop+SLIP;
      else if(lng?h[i]>=pos.target:l[i]<=pos.target)px=pos.target;
      if(px!=null){const pts=lng?px-pos.entry:pos.entry-px;const pnl=pts*pos.size*PV-2*pos.size*FEE;
        eq+=pnl;pk=Math.max(pk,eq);mdd=Math.max(mdd,pk-eq);ds.pnl+=pnl;byd.set(day,(byd.get(day)||0)+pnl);
        if(pnl>0){wins++;gW+=pnl;}else{gL+=Math.abs(pnl);}trades.push({pnl,day});pos=null;i++;continue;}
    }
    if(!pos&&inSess&&mins>=ENT_S&&mins<ENT_E&&ds.pnl>DAY_STOP&&ds.tr<MAX_TR){
      const a=C.atr[i];let d=0; if(a!=null&&a>0){try{d=fn(C,i)||0;}catch{d=0;}}
      if(d){const sp=ex.s*a,tp=ex.t*a,sz=Math.max(1,Math.min(MAXC,Math.floor(RISK_CAP/(sp*PV))));
        const fill=d===1?c[i]+SLIP:c[i]-SLIP;
        pos={dir:d,entry:fill,size:sz,day,stop:d===1?fill-sp:fill+sp,target:d===1?fill+tp:fill-tp};ds.tr++;}
    }
    i++;
  }
  const wd=byd.size?[...byd.values()]:[0],worst=-Math.min(0,...wd);
  return {n:trades.length,win:trades.length?+(wins/trades.length*100).toFixed(1):0,
    pf:gL>0?+(gW/gL).toFixed(2):(gW>0?99:0),net:Math.round(eq),dd:Math.round(mdd),wd:Math.round(worst),
    feasible:mdd<MLL&&worst<DLL};
}

const SRC=process.argv[2]||"58d";
let bars;
if(SRC==="13d"){const Lab=require("./lab-new4.js");bars=Lab.loadCsv(Lab.CSV_13);}
else{bars=JSON.parse(fs.readFileSync(path.join(__dirname,"data","nq-5m.json"),"utf8"));}
bars=bars.filter(b=>b&&isFinite(b.c)).sort((a,b)=>a.t-b.t);
const spanS=new Date(bars[0].t*1000).toISOString().slice(0,10),spanE=new Date(bars[bars.length-1].t*1000).toISOString().slice(0,10);
const C=buildContext(bars);
const EXITS=[
  {tag:"t0.5/s3",s:3.0,t:0.5},{tag:"t0.5/s2",s:2.0,t:0.5},{tag:"t0.75/s2",s:2.0,t:0.75},
  {tag:"t1/s3",s:3.0,t:1.0},{tag:"t1/s2",s:2.0,t:1.0},{tag:"t1/s1.5",s:1.5,t:1.0},
  {tag:"t1.5/s1.5",s:1.5,t:1.5},{tag:"t3/s1",s:1.0,t:3.0},
];
const rows=[];
for(const [key,name,cat,fn] of ENTRIES) for(const ex of EXITS){
  const r=sim(bars,C,fn,ex); if(r.n>=10) rows.push({name:`${name} · ${ex.tag}`,cat,...r});
}
const fmt=r=>r.name.slice(0,34).padEnd(35)+(r.win+"%").padStart(6)+("$"+r.net).padStart(8)+String(r.pf).padStart(6)+String(r.n).padStart(5)+("$"+r.dd).padStart(7)+(r.feasible?" YES":" no ").padStart(5);
console.log(`Tested ${ENTRIES.length}x${EXITS.length}=${ENTRIES.length*EXITS.length} London strategies (${rows.length} with >=10 trades). Data: ${SRC} (${spanS}→${spanE}).\n`);
console.log("### TOP 20 BY WIN RATE (note net$/PF/feasible!):");
console.log("strategy                              win     net$    PF    n    maxDD feas");
rows.slice().sort((a,b)=>b.win-a.win).slice(0,20).forEach(r=>console.log(fmt(r)));
console.log("\n### HIGHEST WIN RATE that is ALSO PROFITABLE + COMBINE-FEASIBLE:");
const good=rows.filter(r=>r.net>0&&r.feasible).sort((a,b)=>b.win-a.win);
if(good.length){good.slice(0,10).forEach(r=>console.log(fmt(r)));}else console.log("  (none — no London strategy is both high-win AND profitable+feasible)");
console.log("\n### For reference, most PROFITABLE London strategies:");
rows.slice().sort((a,b)=>b.net-a.net).slice(0,5).forEach(r=>console.log(fmt(r)));
