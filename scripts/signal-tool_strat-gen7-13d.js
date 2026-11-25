// strat-gen7-13d.js - Generation 7: SPEED TO PASS
// Goal: reach +$3,000 before hitting -$2,000 DD or -$1,000 daily loss
// as FAST as possible (target: under 13 trading days)
//
// What we know works (keep):
//   J10/I9 = Portfolio (morning star OR KeyRev@BB+vol), post-10am filter
//   99% MC, +$5,465-$7,999 full, Combine PASS
//
// Speed levers:
//   1. Larger position size (2-3 MNQ contracts = 2-3x profit per signal)
//   2. More trades per day (3-4/day instead of 2)
//   3. Tighter target (faster lock-in at 1.5x ATR instead of 2x)
//   4. Wider portfolio (more signals = more firing days)
//   5. Scale-in: 2nd trade only if day is already profitable (pyramid winners)
//
// New MC metric: track median DAYS to reach $3k target
"use strict";
const fs=require("fs"),path=require("path");
require("./public/indicators.js");
const I=globalThis.Indicators;
const PV=2,MAXC=5,DLL=1000,MLL=2000,TARGET=3000,TICK=0.25,FEE=0.37,SLIP=2;
const RTH_S=570,RTH_E=960;

function etFast(s){
  const u=s*1000,d=new Date(u),y=d.getUTCFullYear();
  const ms2=new Date(Date.UTC(y,2,1));ms2.setUTCDate(1+((7-ms2.getUTCDay())%7)+7);
  const ns=new Date(Date.UTC(y,10,1));ns.setUTCDate(1+((7-ns.getUTCDay())%7));
  const off=(u>=ms2.getTime()&&u<ns.getTime())?-240:-300;
  const et=new Date(u+off*60000);
  return{day:et.getUTCDay(),mins:et.getUTCHours()*60+et.getUTCMinutes(),
    k:et.getUTCFullYear()+"-"+String(et.getUTCMonth()+1).padStart(2,"0")+"-"+String(et.getUTCDate()).padStart(2,"0")};
}
function preET(bars){
  const n=bars.length,dk=new Array(n),rth=new Array(n),dm=new Array(n),dw=new Array(n);
  for(let i=0;i<n;i++){const p=etFast(bars[i].t);dk[i]=p.k;dw[i]=p.day;dm[i]=p.mins;rth[i]=p.day>=1&&p.day<=5&&p.mins>=RTH_S&&p.mins<RTH_E;}
  return{dk,rth,dm,dw};
}
function buildCtx(bars,ET){
  const n=bars.length;
  const o=bars.map(b=>b.o),h=bars.map(b=>b.h),l=bars.map(b=>b.l),c=bars.map(b=>b.c),v=bars.map(b=>b.v||0);
  const ema9=I.ema(c,9),ema21=I.ema(c,21),ema200=I.ema(c,200);
  const atr=I.atr(h,l,c,14),rsi14=I.rsi(c,14),rsi2=I.rsi(c,2);
  const bb20=I.sma(c,20),bbS=I.stdev(c,20);
  const bbU=bb20.map((v2,i2)=>v2==null?null:v2+2*bbS[i2]);
  const bbL=bb20.map((v2,i2)=>v2==null?null:v2-2*bbS[i2]);
  const vol20=I.sma(v,20);
  const vwap=new Array(n).fill(null),vsd=new Array(n).fill(null);
  const hod=new Array(n).fill(null),lod=new Array(n).fill(null),dopen=new Array(n).fill(null);
  const pdH=new Array(n).fill(null),pdL=new Array(n).fill(null),pdC=new Array(n).fill(null);
  const orH=new Array(n).fill(null),orL=new Array(n).fill(null);
  let vN=0,vD=0,vN2=0,curD=null,hi=-Infinity,lo=Infinity,op=null,oRH=-Infinity,oRL=Infinity;
  const dH=new Map(),dL=new Map(),dC=new Map(),order=[];
  for(let i=0;i<n;i++){
    const dk=ET.dk[i],inR=ET.rth[i],mins=ET.dm[i],dow=ET.dw[i];
    if(dk!==curD){
      if(curD){dH.set(curD,hi);dL.set(curD,lo);dC.set(curD,c[i-1]);order.push(curD);}
      vN=vD=vN2=0;hi=-Infinity;lo=Infinity;op=null;oRH=-Infinity;oRL=Infinity;curD=dk;
    }
    if(inR){
      if(op==null)op=o[i];
      hi=Math.max(hi,h[i]);lo=Math.min(lo,l[i]);
      const hlc3=(h[i]+l[i]+c[i])/3,vol=v[i]||1;
      vN+=hlc3*vol;vN2+=hlc3*hlc3*vol;vD+=vol;
      if(vD>0){const m=vN/vD;vwap[i]=m;vsd[i]=Math.sqrt(Math.max(0,vN2/vD-m*m));}
      if(dow>=1&&dow<=5&&mins>=RTH_S&&mins<RTH_S+30){oRH=Math.max(oRH,h[i]);oRL=Math.min(oRL,l[i]);}
    }
    hod[i]=hi===-Infinity?null:hi;lod[i]=lo===Infinity?null:lo;dopen[i]=op;
    orH[i]=oRH===-Infinity?null:oRH;orL[i]=oRL===Infinity?null:oRL;
    const prev=order[order.length-1];
    if(prev){pdH[i]=dH.get(prev);pdL[i]=dL.get(prev);pdC[i]=dC.get(prev);}
  }
  const hiVol=new Array(n).fill(false);
  for(let i=0;i<n;i++)if(vol20[i]!=null)hiVol[i]=(v[i]||0)>1.5*vol20[i];
  return{o,h,l,c,v,n,ema9,ema21,ema200,atr,rsi14,rsi2,bbU,bbL,bb20,bbS,vol20,
    vwap,vsd,hod,lod,dopen,orH,orL,pdH,pdL,pdC,hiVol,etMins:ET.dm,etRTH:ET.rth};
}

function morningStarDir(C,i){
  if(i<2||C.atr[i]==null)return 0;
  const a=C.atr[i];
  const b2=Math.abs(C.c[i-2]-C.o[i-2]),b1=Math.abs(C.c[i-1]-C.o[i-1]),b0=Math.abs(C.c[i]-C.o[i]);
  if(b2<0.5*a||b1>0.4*a||b0<0.4*a)return 0;
  if(C.c[i-2]<C.o[i-2]&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-2])return 1;
  if(C.c[i-2]>C.o[i-2]&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-2])return -1;
  return 0;
}
function keyRevBBVol(C,i){
  if(i<5||C.bbU[i]==null||!C.hiVol[i])return 0;
  let nl=true,nh=true;
  for(let q=1;q<=5;q++){if(C.l[i]>=C.l[i-q])nl=false;if(C.h[i]<=C.h[i-q])nh=false;}
  if(nl&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-1]&&C.l[i]<=C.bbL[i]&&C.c[i]>C.bbL[i])return 1;
  if(nh&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-1]&&C.h[i]>=C.bbU[i]&&C.c[i]<C.bbU[i])return -1;
  return 0;
}
function twoBarPullback(C,i){
  if(i<4||C.ema200[i]==null||C.vwap[i]==null||C.atr[i]==null)return 0;
  const upTrend=C.c[i]>C.ema200[i]&&C.c[i]>C.vwap[i];
  const dnTrend=C.c[i]<C.ema200[i]&&C.c[i]<C.vwap[i];
  const pullDn=C.c[i-2]<C.c[i-3]&&C.c[i-1]<C.c[i-2];
  const pullUp=C.c[i-2]>C.c[i-3]&&C.c[i-1]>C.c[i-2];
  const rng=C.h[i]-C.l[i];
  if(upTrend&&pullDn&&C.c[i]>C.o[i]&&(C.c[i]-C.l[i])/Math.max(rng,0.001)>0.6&&C.c[i]>C.c[i-1])return 1;
  if(dnTrend&&pullUp&&C.c[i]<C.o[i]&&(C.h[i]-C.c[i])/Math.max(rng,0.001)>0.6&&C.c[i]<C.c[i-1])return -1;
  return 0;
}

// Portfolio signal functions
function sigI9(C,i){return morningStarDir(C,i)||keyRevBBVol(C,i)||0;}
function sigJ10(C,i){
  if(C.etMins==null||C.etMins[i]<600||C.etMins[i]>=930)return 0;
  return morningStarDir(C,i)||keyRevBBVol(C,i)||0;
}
function sigTriple(C,i){
  return morningStarDir(C,i)||keyRevBBVol(C,i)||twoBarPullback(C,i)||0;
}
function sigTripleFiltered(C,i){
  if(C.etMins==null||C.etMins[i]<600||C.etMins[i]>=930)return 0;
  return morningStarDir(C,i)||keyRevBBVol(C,i)||twoBarPullback(C,i)||0;
}

function sim(bars,C,ET,fn,p){
  const slip=(p.slipTicks||0)*TICK,fee=p.fee||0;
  let eq=0,pk=0,mdd=0,wins=0,gW=0,gL=0;
  const trades=[],byd=new Map();
  let pos=null,ds={k:null,real:0,tr:0,dayPnL:0};
  let i=210;
  while(i<bars.length){
    const b=bars[i],dk=ET.dk[i],inR=ET.rth[i];
    if(dk!==ds.k)ds={k:dk,real:0,tr:0,dayPnL:0};
    if(pos){
      const lng=pos.dir===1;let px=null;
      if(dk!==pos.day||!inR)px=lng?bars[i-1].c-slip:bars[i-1].c+slip;
      else if(lng?b.l<=pos.stop:b.h>=pos.stop)px=lng?pos.stop-slip:pos.stop+slip;
      else if(lng?b.h>=pos.target:b.l<=pos.target)px=pos.target;
      if(px!=null){
        const pts=lng?px-pos.entry:pos.entry-px,pnl=pts*pos.size*PV-2*pos.size*fee;
        eq+=pnl;pk=Math.max(pk,eq);mdd=Math.max(mdd,pk-eq);
        ds.real+=pnl;byd.set(dk,(byd.get(dk)||0)+pnl);
        if(pnl>0){wins++;gW+=pnl;}else gL+=Math.abs(pnl);
        trades.push({pnl,day:dk,dir:pos.dir,pts});pos=null;i++;continue;
      }
    }
    if(!pos&&inR&&ds.real>p.dayStop&&ds.tr<p.maxTr){
      const a=C.atr[i];let d=0;
      try{d=fn(C,i)||0;}catch(_){}
      if(d&&a!=null&&a>0){
        const sp=p.stopMult*a;
        const sz=Math.max(1,Math.min(MAXC,Math.floor(p.riskCap/(sp*PV))));
        const fill=d===1?C.c[i]+slip:C.c[i]-slip;
        pos={dir:d,entry:fill,size:sz,day:dk,
          stop:d===1?fill-sp:fill+sp,
          target:d===1?fill+p.tgtMult*a:fill-p.tgtMult*a};
        ds.tr++;
      }
    }
    i++;
  }
  const n2=trades.length,wdV=byd.size?[...byd.values()]:[0];
  return{n:n2,win:n2?+(wins/n2*100).toFixed(1):0,
    pf:gL>0?+(gW/gL).toFixed(2):(gW>0?99:0),
    net$:Math.round(eq),maxDD$:Math.round(mdd),
    worstDay$:Math.round(-Math.min(0,...wdV)),
    feasible:mdd<MLL&&(-Math.min(0,...wdV))<DLL,trades,byd};
}

// Enhanced cPass: returns pass status AND days to reach target
function cPass(trades){
  let cum=0,pk=0;
  const bd=new Map(),daysSeen=new Set();
  for(const t of trades){
    daysSeen.add(t.day);
    cum+=t.pnl;pk=Math.max(pk,cum);
    bd.set(t.day,(bd.get(t.day)||0)+t.pnl);
    if(pk-cum>=MLL)return{passed:false,why:"MLL",days:daysSeen.size};
    if(bd.get(t.day)<=-DLL)return{passed:false,why:"DLL",days:daysSeen.size};
    if(cum>=TARGET)return{passed:true,why:"target",days:daysSeen.size};
  }
  return{passed:false,why:"no-target",days:daysSeen.size};
}

// Enhanced MC: track pass%, median days to pass, % under 13 days
function mc(trades,iters){
  iters=iters||2000;if(!trades.length)return{pct:0,medDays:null,under13:0};
  const p=trades.map(t=>t.pnl),d=trades.map(t=>t.day);
  let pass=0,under13=0;const passDays=[];
  for(let it=0;it<iters;it++){
    // Fisher-Yates on indices
    const idx=Array.from({length:p.length},(_,k)=>k);
    for(let k=idx.length-1;k>0;k--){const j=(Math.random()*(k+1))|0;const t=idx[k];idx[k]=idx[j];idx[j]=t;}
    let cum=0,pk=0,ok=false,dead=false;
    const daysSeen=new Set();
    for(let k=0;k<idx.length;k++){
      const ii=idx[k];
      daysSeen.add(d[ii]);
      cum+=p[ii];pk=Math.max(pk,cum);
      if(pk-cum>=MLL){dead=true;break;}
      if(cum>=TARGET){ok=true;break;}
    }
    if(ok&&!dead){pass++;passDays.push(daysSeen.size);if(daysSeen.size<=13)under13++;}
  }
  passDays.sort((a,b)=>a-b);
  const med=passDays.length?passDays[Math.floor(passDays.length/2)]:null;
  return{pct:+(pass/iters*100).toFixed(1),medDays:med,under13:pass>0?+(under13/pass*100).toFixed(0):0};
}

// Strategy definitions: [name, signalFn, config override or null]
// All reference p.riskCap, p.maxTr, p.stopMult, p.tgtMult for flexibility
const METHODS=[
  // K1: I9 baseline (best from Gen-5/6) — reference
  ["K1: I9 baseline (star+rev)", sigI9],
  // K2: J10 filtered baseline — reference
  ["K2: J10 10am+ filter", sigJ10],
  // K3: I9 with 3 trades/day
  ["K3: I9 x3/day", sigI9],
  // K4: J10 with 3 trades/day
  ["K4: J10 x3/day", sigJ10],
  // K5: Triple portfolio (star+rev+pullback) filtered 10am+
  ["K5: Triple filtered 10am+", sigTripleFiltered],
  // K6: Triple portfolio unfiltered x3/day
  ["K6: Triple x3/day", sigTriple],
  // K7: J10 bigger size ($400 risk cap -> 2 contracts more often)
  ["K7: J10 bigger size $400", sigJ10],
  // K8: I9 bigger size $400
  ["K8: I9 bigger size $400", sigI9],
  // K9: Triple filtered + bigger size
  ["K9: Triple filtered $400", sigTripleFiltered],
  // K10: J10 max aggression ($500, 3/day)
  ["K10: J10 max aggro $500 3/d", sigJ10],
  // K11: Triple filtered max aggression
  ["K11: Triple filtered $500 3/d", sigTripleFiltered],
  // K12: I9 + tighter target (1.5x instead of 2x) - more frequent locks
  ["K12: I9 tight target 1.5x", sigI9],
];

// Config per strategy index
const STRATEGY_CONFIGS=[
  // K1 reference
  [{stopMult:1.5,tgtMult:2.0,riskCap:200,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.5,tgtMult:2.5,riskCap:200,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP}],
  // K2 reference
  [{stopMult:1.5,tgtMult:2.0,riskCap:350,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.5,tgtMult:2.5,riskCap:350,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP}],
  // K3 I9 x3/day
  [{stopMult:1.5,tgtMult:2.0,riskCap:200,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.5,tgtMult:2.5,riskCap:200,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.2,tgtMult:2.0,riskCap:200,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP}],
  // K4 J10 x3/day
  [{stopMult:1.5,tgtMult:2.0,riskCap:350,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.5,tgtMult:2.5,riskCap:350,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.2,tgtMult:2.0,riskCap:350,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP}],
  // K5 triple filtered
  [{stopMult:1.5,tgtMult:2.0,riskCap:200,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.5,tgtMult:3.0,riskCap:200,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.2,tgtMult:2.0,riskCap:200,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP}],
  // K6 triple unfiltered x3/day
  [{stopMult:1.5,tgtMult:2.0,riskCap:200,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.5,tgtMult:2.5,riskCap:200,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.2,tgtMult:2.5,riskCap:200,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP}],
  // K7 J10 $400
  [{stopMult:1.5,tgtMult:2.0,riskCap:400,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.5,tgtMult:2.5,riskCap:400,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP}],
  // K8 I9 $400
  [{stopMult:1.5,tgtMult:2.0,riskCap:400,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.5,tgtMult:2.5,riskCap:400,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP}],
  // K9 triple filtered $400
  [{stopMult:1.5,tgtMult:2.0,riskCap:400,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.5,tgtMult:2.5,riskCap:400,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.2,tgtMult:2.0,riskCap:400,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP}],
  // K10 J10 max $500 3/day
  [{stopMult:1.5,tgtMult:2.0,riskCap:500,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.5,tgtMult:2.5,riskCap:500,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.2,tgtMult:2.0,riskCap:500,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP}],
  // K11 triple filtered $500 3/day
  [{stopMult:1.5,tgtMult:2.0,riskCap:500,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.5,tgtMult:2.5,riskCap:500,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.2,tgtMult:2.5,riskCap:500,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP}],
  // K12 I9 tight target
  [{stopMult:1.5,tgtMult:1.5,riskCap:200,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.2,tgtMult:1.5,riskCap:200,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
   {stopMult:1.0,tgtMult:1.5,riskCap:350,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP}],
];

const dol=x=>(x>=0?"+$":"-$")+Math.abs(Math.round(x)).toLocaleString();
const pct=x=>x.toFixed(1)+"%";

(function main(){
  console.log("Gen-7 SPEED-TO-PASS loading...");
  const allBars=JSON.parse(fs.readFileSync(path.join(__dirname,"data","nq-5m.json"),"utf8"))
    .filter(b=>b&&isFinite(b.c)).sort((a,b)=>a.t-b.t);
  const ET=preET(allBars);
  const daySet=new Set();
  for(let i=0;i<allBars.length;i++)if(ET.rth[i])daySet.add(ET.dk[i]);
  const rthDays=Array.from(daySet).sort();
  const last13=rthDays.slice(-13);
  const cutT=(()=>{for(let i=0;i<allBars.length;i++)if(ET.dk[i]===last13[0])return allBars[i].t;return Infinity;})();
  console.log("13d window: "+last13[0]+" to "+last13[last13.length-1]+" | Total RTH days: "+rthDays.length);
  const C=buildCtx(allBars,ET);
  function run13(fn,p){return sim(allBars,C,ET,(C2,i)=>allBars[i].t>=cutT?fn(C2,i):0,p);}
  function runFull(fn,p){return sim(allBars,C,ET,fn,p);}

  const results=[];
  for(let mi=0;mi<METHODS.length;mi++){
    const name=METHODS[mi][0],fn=METHODS[mi][1];
    const cfgs=STRATEGY_CONFIGS[mi];
    process.stdout.write("  "+(mi+1)+"/"+METHODS.length+" "+name+"... ");
    let best13=-Infinity,bestR=null,bestCfg=null;
    for(let ci=0;ci<cfgs.length;ci++){
      const p=cfgs[ci];
      const r13=run13(fn,p),rF=runFull(fn,p);
      if(r13.net$>best13){
        best13=r13.net$;
        const cp=cPass(rF.trades),m=mc(rF.trades);
        bestR={r13,rF,cp,m};bestCfg=p;
      }
    }
    const tag=bestR.rF.feasible&&bestR.rF.net$>0?" OK":" --";
    const daysStr=bestR.cp.passed?"in "+bestR.cp.days+"d":"FAIL";
    console.log("13d "+dol(bestR.r13.net$)+" | full "+dol(bestR.rF.net$)+tag+" | "+daysStr+" | MC med="+bestR.m.medDays+"d u13="+bestR.m.under13+"%");
    results.push({name,cfg:bestCfg,r13:bestR.r13,rF:bestR.rF,cp:bestR.cp,mcData:bestR.m});
  }

  // Sort: pass in fewest days first (among passers), then by MC under-13
  results.sort((a,b)=>{
    const ap=a.cp.passed,bp=b.cp.passed;
    const af=a.rF.feasible&&a.rF.net$>0,bf=b.rF.feasible&&b.rF.net$>0;
    if(ap&&!bp)return -1;if(!ap&&bp)return 1;
    if(ap&&bp){
      if(a.cp.days!==b.cp.days)return a.cp.days-b.cp.days; // fewer days first
    }
    if(af&&!bf)return -1;if(!af&&bf)return 1;
    return b.mcData.under13-a.mcData.under13;
  });

  console.log("\n"+"=".repeat(155));
  console.log("  GEN-7 SPEED-TO-PASS — sorted by: Combine PASS first, then fewest days to $3k");
  console.log("=".repeat(155));
  console.log("Strategy".padEnd(36)+"Config".padEnd(26)+"13d".padStart(9)+"Full".padStart(10)+"DD".padStart(8)+"Feas".padStart(5)+" Combine".padStart(9)+"DaysPass".padStart(9)+"MC%".padStart(6)+"MedDays".padStart(8)+"U13%".padStart(6));
  console.log("-".repeat(155));
  for(const r of results){
    const cfg="s"+r.cfg.stopMult+"/t"+r.cfg.tgtMult+" $"+r.cfg.riskCap+" "+r.cfg.maxTr+"/d";
    const star=(r.rF.feasible&&r.rF.net$>0)?"*":" ";
    const cpStr=r.cp.passed?"PASS":"FAIL";
    const dStr=r.cp.passed?String(r.cp.days):"--";
    console.log((star+r.name).slice(0,35).padEnd(36)+cfg.padEnd(26)+
      dol(r.r13.net$).padStart(9)+dol(r.rF.net$).padStart(10)+("-$"+r.rF.maxDD$).padStart(8)+
      (r.rF.feasible?"Y":"N").padStart(5)+cpStr.padStart(9)+dStr.padStart(9)+
      String(r.mcData.pct+"%").padStart(6)+String(r.mcData.medDays||"--").padStart(8)+
      String(r.mcData.under13+"%").padStart(6));
  }

  const passers=results.filter(r=>r.cp.passed);
  console.log("\n=== COMBINE PASSERS: "+passers.length+"/"+results.length+" ===");
  if(passers.length){
    console.log("Best (fewest days): "+passers[0].name+" in "+passers[0].cp.days+" trading days");
    console.log("MC under-13 leader: "+[...passers].sort((a,b)=>b.mcData.under13-a.mcData.under13)[0].name+" "+[...passers].sort((a,b)=>b.mcData.under13-a.mcData.under13)[0].mcData.under13+"% of shuffles pass in <=13 days");
  }

  console.log("\nDETAIL — TOP 4:");
  for(let ti=0;ti<Math.min(4,results.length);ti++){
    const r=results[ti];
    console.log("\n["+(ti+1)+"] "+r.name+" | cfg: s"+r.cfg.stopMult+"/t"+r.cfg.tgtMult+" $"+r.cfg.riskCap+" "+r.cfg.maxTr+"/d");
    console.log("    13d: "+dol(r.r13.net$)+" | "+r.r13.n+"t | "+pct(r.r13.win)+" win | PF "+r.r13.pf+" | DD -$"+r.r13.maxDD$);
    console.log("    Full: "+dol(r.rF.net$)+" | "+r.rF.n+"t | "+pct(r.rF.win)+" | DD -$"+r.rF.maxDD$+" | "+(r.rF.feasible?"FEASIBLE":"BUST"));
    console.log("    Combine: "+(r.cp.passed?"PASS in "+r.cp.days+" days":"FAIL("+r.cp.why+")")+" | MC: "+r.mcData.pct+"% | Median days: "+r.mcData.medDays+" | Under-13: "+r.mcData.under13+"%");
    if(r.r13.byd&&r.r13.byd.size){
      const s=Array.from(r.r13.byd.entries()).sort((a,b)=>a[0].localeCompare(b[0]));
      let cum13=0;
      for(const[day,pnl]of s){cum13+=pnl;console.log("      "+day+": "+dol(pnl)+" (running: "+dol(cum13)+")");}
    }
  }

  // Save markdown
  const lines=["# Gen-7: Speed-to-Pass Strategy Battle ("+new Date().toISOString().slice(0,10)+")",
    "","**Goal:** reach +$3,000 before -$2,000 DD or -$1,000 daily loss, as fast as possible.","",
    "| # | Strategy | Config | 13d | Full | DD | F | Combine | Days | MC% | MedDays | U13% |",
    "|---|---|---|---:|---:|---:|:--:|:---:|---:|---:|---:|---:|"];
  for(let ri=0;ri<results.length;ri++){
    const r=results[ri];
    const star=r.rF.feasible&&r.rF.net$>0?"*":"";
    lines.push("| "+(ri+1)+" | "+star+r.name+" | s"+r.cfg.stopMult+"/t"+r.cfg.tgtMult+" $"+r.cfg.riskCap+" "+r.cfg.maxTr+"/d | "+
      dol(r.r13.net$)+" | "+dol(r.rF.net$)+" | -$"+r.rF.maxDD$+" | "+(r.rF.feasible?"Y":"N")+" | "+
      (r.cp.passed?"PASS":"FAIL-"+r.cp.why)+" | "+(r.cp.passed?r.cp.days:"--")+" | "+
      r.mcData.pct+"% | "+(r.mcData.medDays||"--")+" | "+r.mcData.under13+"% |");
  }
  lines.push("","## Key","- **Days**: trading days to reach +$3k in the actual trade sequence",
    "- **MC%**: % of 2000 random orderings that still PASS the combine",
    "- **MedDays**: median trading days to pass across all MC passing runs",
    "- **U13%**: % of MC passing runs that passed in 13 days or fewer",
    "","## Top 4 Detail","");
  for(let ti=0;ti<Math.min(4,results.length);ti++){
    const r=results[ti];
    lines.push("### "+(ti+1)+". "+r.name);
    lines.push("- **Config:** s"+r.cfg.stopMult+"/t"+r.cfg.tgtMult+" $"+r.cfg.riskCap+" "+r.cfg.maxTr+"/d");
    lines.push("- **13d:** "+dol(r.r13.net$)+" | "+r.r13.n+"t | "+pct(r.r13.win)+" win | PF "+r.r13.pf+" | DD -$"+r.r13.maxDD$);
    lines.push("- **Full:** "+dol(r.rF.net$)+" | "+r.rF.n+"t | "+pct(r.rF.win)+" | DD -$"+r.rF.maxDD$+" | "+(r.rF.feasible?"FEASIBLE":"BUST"));
    lines.push("- **Combine:** "+(r.cp.passed?"PASS in "+r.cp.days+" trading days":"FAIL ("+r.cp.why+")")+" | MC: "+r.mcData.pct+"% | Median: "+r.mcData.medDays+"d | Under-13: "+r.mcData.under13+"%");
    if(r.r13.byd&&r.r13.byd.size){
      lines.push("","| Date | Day P&L | Running Total |","|---|---|---|");
      const s=Array.from(r.r13.byd.entries()).sort((a,b)=>a[0].localeCompare(b[0]));
      let cum13=0;
      for(const[d,p2]of s){cum13+=p2;lines.push("| "+d+" | "+dol(p2)+" | "+dol(cum13)+" |");}
    }
    lines.push("");
  }
  fs.writeFileSync(path.join(__dirname,"logs","strat-gen7-speed-report.md"),lines.join("\n")+"\n");
  console.log("\nSaved: logs/strat-gen7-speed-report.md");
})();
