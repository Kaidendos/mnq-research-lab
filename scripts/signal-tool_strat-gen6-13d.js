// strat-gen6-13d.js - Generation 6
// LESSONS ENCODED:
//   I9 (portfolio) = 99% MC, Combine PASS, +$5,465 full — BUILD ON THIS
//   I12 (two-bar pullback) = 74% MC, +$2,918 full — REFINE
//   Morning star + KeyRev+volume = complementary patterns, use both
// NEW ANGLES:
//   J1: Triple portfolio (I9 + I12 two-bar pullback) 
//   J2: I9 with tighter params tuning (s1.0/t2.5, riskCap tuning)
//   J3: RSI2 extreme + key reversal (classic mean-reversion)
//   J4: VWAP sigma-band touch (1.5σ touch + reversal bar)
//   J5: Opening drive fade (first 15m big move, fade after OR break)
//   J6: Gap fill — morning gap to OR then fade the fill
//   J7: Late-day exhaustion (3pm ET: if up 1.5 ATR fade, if down 1.5 ATR fade)
//   J8: Prior day high/low reaction + volume spike
//   J9: Double bottom / double top (2 tests of level within 10 bars, 2nd test reversal)
//   J10: Morning star at VWAP sigma (1σ band = dynamic support)
//   J11: Narrow range inside bar + breakout at BB extreme  
//   J12: Triple portfolio (I9 + I12 + I6 10am reversal)
"use strict";
const fs=require("fs"),path=require("path");
require("./public/indicators.js");
const I=globalThis.Indicators;
const PV=2,MAXC=5,DLL=1000,MLL=2000,TARGET=3000,TICK=0.25,FEE=0.37,SLIP=2;
const RTH_S=570,RTH_E=960;

function etFast(s){
  const u=s*1000,d=new Date(u),y=d.getUTCFullYear();
  const ms=new Date(Date.UTC(y,2,1));ms.setUTCDate(1+((7-ms.getUTCDay())%7)+7);
  const ns=new Date(Date.UTC(y,10,1));ns.setUTCDate(1+((7-ns.getUTCDay())%7));
  const off=(u>=ms.getTime()&&u<ns.getTime())?-240:-300;
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
  const bbU=bb20.map((v2,i)=>v2==null?null:v2+2*bbS[i]);
  const bbL=bb20.map((v2,i)=>v2==null?null:v2-2*bbS[i]);
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
  const lowVol=new Array(n).fill(false);
  for(let i=0;i<n;i++)if(vol20[i]!=null)lowVol[i]=(v[i]||0)<0.6*vol20[i];
  const hiVol=new Array(n).fill(false);
  for(let i=0;i<n;i++)if(vol20[i]!=null)hiVol[i]=(v[i]||0)>1.5*vol20[i];

  return{o,h,l,c,v,n,ema9,ema21,ema200,atr,rsi14,rsi2,bbU,bbL,bb20,bbS,vol20,
    vwap,vsd,hod,lod,dopen,orH,orL,pdH,pdL,pdC,lowVol,hiVol,
    etMins:ET.dm,etRTH:ET.rth};
}

function keyRevDir(C,i){
  if(i<5)return 0;
  let nl=true,nh=true;
  for(let q=1;q<=5;q++){if(C.l[i]>=C.l[i-q])nl=false;if(C.h[i]<=C.h[i-q])nh=false;}
  if(nl&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-1])return 1;
  if(nh&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-1])return -1;
  return 0;
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

function sim(bars,C,ET,fn,p){
  const slip=(p.slipTicks||0)*TICK,fee=p.fee||0;
  let eq=0,pk=0,mdd=0,wins=0,gW=0,gL=0;
  const trades=[],byd=new Map();
  let pos=null,ds={k:null,real:0,tr:0};
  let i=210;
  while(i<bars.length){
    const b=bars[i],dk=ET.dk[i],inR=ET.rth[i];
    if(dk!==ds.k)ds={k:dk,real:0,tr:0};
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
        const sp=p.stopMult*a,sz=Math.max(1,Math.min(MAXC,Math.floor(p.riskCap/(sp*PV))));
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
function cPass(trades){
  let cum=0,pk=0;const bd=new Map();
  for(const t of trades){
    cum+=t.pnl;pk=Math.max(pk,cum);bd.set(t.day,(bd.get(t.day)||0)+t.pnl);
    if(pk-cum>=MLL)return{passed:false,why:"MLL"};
    if(bd.get(t.day)<=-DLL)return{passed:false,why:"DLL"};
    if(cum>=TARGET)return{passed:true,why:"target"};
  }return{passed:false,why:"no-target"};
}
function mc(trades,iters){
  iters=iters||2000;if(!trades.length)return 0;
  const p=trades.map(t=>t.pnl);let pass=0;
  for(let it=0;it<iters;it++){
    for(let k=p.length-1;k>0;k--){const j=(Math.random()*(k+1))|0;const t=p[k];p[k]=p[j];p[j]=t;}
    let cum=0,pk=0,ok=false,dead=false;
    for(let k=0;k<p.length;k++){cum+=p[k];pk=Math.max(pk,cum);if(pk-cum>=MLL){dead=true;break;}if(cum>=TARGET){ok=true;break;}}
    if(ok&&!dead)pass++;
  }return+(pass/iters*100).toFixed(1);
}

const METHODS=[

// J1: Triple portfolio — morning star OR KeyRev@BB+vol OR two-bar pullback
// I9 (morning star + KeyRev) = 99% MC. Adding I12 (two-bar pullback = 74% MC) 
// as a 3rd signal should fill even more gaps with high-quality setups
["J1: Triple portfolio (star+rev+pullback)", function(C,i){
  if(i<5||C.atr[i]==null)return 0;
  // Arm 1: morning star
  const ms=morningStarDir(C,i);if(ms)return ms;
  // Arm 2: KeyRev@BB + high volume
  if(C.bbU[i]!=null&&C.hiVol[i]){
    let nl=true,nh=true;
    for(let q=1;q<=5;q++){if(C.l[i]>=C.l[i-q])nl=false;if(C.h[i]<=C.h[i-q])nh=false;}
    if(nl&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-1]&&C.l[i]<=C.bbL[i]&&C.c[i]>C.bbL[i])return 1;
    if(nh&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-1]&&C.h[i]>=C.bbU[i]&&C.c[i]<C.bbU[i])return -1;
  }
  // Arm 3: two-bar pullback in trend
  if(C.ema200[i]!=null&&C.vwap[i]!=null){
    const upTrend=C.c[i]>C.ema200[i]&&C.c[i]>C.vwap[i];
    const dnTrend=C.c[i]<C.ema200[i]&&C.c[i]<C.vwap[i];
    const twoPullDn=C.c[i-2]<C.c[i-3]&&C.c[i-1]<C.c[i-2];
    const twoPullUp=C.c[i-2]>C.c[i-3]&&C.c[i-1]>C.c[i-2];
    const rng=C.h[i]-C.l[i];
    const strongBull=C.c[i]>C.o[i]&&(C.c[i]-C.l[i])/Math.max(rng,0.001)>0.6;
    const strongBear=C.c[i]<C.o[i]&&(C.h[i]-C.c[i])/Math.max(rng,0.001)>0.6;
    if(upTrend&&twoPullDn&&strongBull&&C.c[i]>C.c[i-1])return 1;
    if(dnTrend&&twoPullUp&&strongBear&&C.c[i]<C.c[i-1])return -1;
  }
  return 0;
}],

// J2: I9 exact replica but with aggressive risk cap to size up on best signals
// I9 ran $200 risk cap → usually 1 MNQ. What if we push to $350 risk cap
// (still under daily stop) to size 2 contracts when ATR is low?
["J2: Portfolio G8+S10 bigger size", function(C,i){
  if(i<5||C.atr[i]==null)return 0;
  const ms=morningStarDir(C,i);if(ms)return ms;
  if(C.bbU[i]==null||C.hiVol[i]==null)return 0;
  if(!C.hiVol[i])return 0;
  let nl=true,nh=true;
  for(let q=1;q<=5;q++){if(C.l[i]>=C.l[i-q])nl=false;if(C.h[i]<=C.h[i-q])nh=false;}
  if(nl&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-1]&&C.l[i]<=C.bbL[i]&&C.c[i]>C.bbL[i])return 1;
  if(nh&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-1]&&C.h[i]>=C.bbU[i]&&C.c[i]<C.bbU[i])return -1;
  return 0;
}],

// J3: RSI2 extreme + key reversal
// RSI(2) below 5 = massively oversold in very short term
// RSI(2) above 95 = massively overbought
// Add a key reversal bar to confirm the turn — classic swing trade filter
["J3: RSI2 extreme + key reversal", function(C,i){
  if(C.rsi2[i]==null||C.atr[i]==null)return 0;
  const d=keyRevDir(C,i);if(!d)return 0;
  if(d===1&&C.rsi2[i]<10)return 1;
  if(d===-1&&C.rsi2[i]>90)return -1;
  return 0;
}],

// J4: VWAP sigma-band touch + reversal
// VWAP +/- 1σ = standard deviation band around fair value
// A touch of 1σ + reversal bar = mean reversion from statistically stretched level
// This is cleaner than 2σ BB because it's session-anchored
["J4: VWAP 1-sigma touch + reversal", function(C,i){
  if(C.vwap[i]==null||C.vsd[i]==null||C.atr[i]==null)return 0;
  const vw=C.vwap[i],sd=C.vsd[i];
  if(sd<0.1*C.atr[i])return 0; // need meaningful sigma
  const d=keyRevDir(C,i);if(!d)return 0;
  if(d===1&&C.l[i]<=vw-sd&&C.c[i]>vw-sd)return 1;
  if(d===-1&&C.h[i]>=vw+sd&&C.c[i]<vw+sd)return -1;
  return 0;
}],

// J5: Opening drive momentum (NOT a fade — ride the open)
// Lesson from power hour (H9) and 10am reversal (I6): the open matters
// Specifically: first strong bar at 9:35 in the direction of the gap
// + OR direction alignment = continuation trade on the opening drive
// Ride the early momentum, not fight it
["J5: Opening drive continuation", function(C,i){
  if(C.etMins[i]==null||C.dopen[i]==null||C.atr[i]==null||C.orH[i]==null)return 0;
  const mins=C.etMins[i];
  if(mins<575||mins>=600)return 0; // 9:35-9:55 ET (after 1st bar)
  if(C.orH[i]-C.orL[i]<0.5*C.atr[i])return 0;
  // Gap direction: dopen vs pdC
  if(C.pdC[i]==null)return 0;
  const gapUp=C.dopen[i]>C.pdC[i]+0.2*C.atr[i];
  const gapDn=C.dopen[i]<C.pdC[i]-0.2*C.atr[i];
  // Strong bull bar, gap up, price above dopen
  if(gapUp&&C.c[i]>C.dopen[i]&&C.c[i]>C.o[i]&&(C.c[i]-C.o[i])>0.4*C.atr[i])return 1;
  if(gapDn&&C.c[i]<C.dopen[i]&&C.c[i]<C.o[i]&&(C.o[i]-C.c[i])>0.4*C.atr[i])return -1;
  return 0;
}],

// J6: Prior day high/low + key reversal + high volume
// PDH and PDL are the MOST referenced levels by institutional order flow
// A key reversal at PDH/PDL with volume surge = institutions defending the level
["J6: Prior day high/low reaction + vol", function(C,i){
  if(C.pdH[i]==null||C.atr[i]==null||!C.hiVol[i])return 0;
  const tol=0.25*C.atr[i];
  const d=keyRevDir(C,i);if(!d)return 0;
  // Test of PDH → rejection (short)
  if(d===-1&&Math.abs(C.h[i]-C.pdH[i])<tol&&C.c[i]<C.pdH[i])return -1;
  // Test of PDL → bounce (long)
  if(d===1&&Math.abs(C.l[i]-C.pdL[i])<tol&&C.c[i]>C.pdL[i])return 1;
  return 0;
}],

// J7: Late-day exhaustion fade (3:00-3:30 PM ET)
// The last 30 min before power hour often sees an exhaustion of the day's trend
// If the day is up 2+ ATR by 3pm, it's extended — fade the move
["J7: Late-day exhaustion fade", function(C,i){
  if(C.etMins[i]==null||C.dopen[i]==null||C.atr[i]==null||C.vwap[i]==null)return 0;
  const mins=C.etMins[i];
  if(mins<900||mins>=930)return 0; // 3:00-3:30 ET
  const dayMove=C.c[i]-C.dopen[i];
  // Day is extended AND current bar is reversing
  if(dayMove>1.5*C.atr[i]&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-1]&&C.c[i]<C.vwap[i])return -1;
  if(dayMove<-1.5*C.atr[i]&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-1]&&C.c[i]>C.vwap[i])return 1;
  return 0;
}],

// J8: Double bottom / double top (within 10 bars)
// Two tests of the same level (within 0.3 ATR) within 10 bars
// 2nd test must fail to make new extreme → confirmed reversal
// This is one of the most reliable classical patterns
["J8: Double bottom / double top", function(C,i){
  if(i<10||C.atr[i]==null)return 0;
  const tol=0.3*C.atr[i];
  // Find prior low/high in last 3-10 bars (not too close, not too far)
  let priorL=null,priorH=null;
  for(let k=i-10;k<i-2;k++){
    if(k<0)continue;
    // Prior low: a bar lower than neighbors
    if(C.l[k]<C.l[k-1]&&C.l[k]<C.l[k+1]){if(priorL===null||C.l[k]<priorL)priorL=C.l[k];}
    if(C.h[k]>C.h[k-1]&&C.h[k]>C.h[k+1]){if(priorH===null||C.h[k]>priorH)priorH=C.h[k];}
  }
  // Double bottom: current low near prior low but doesn't make new low, reverses up
  if(priorL!==null&&Math.abs(C.l[i]-priorL)<tol&&C.l[i]>=priorL&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-1])return 1;
  if(priorH!==null&&Math.abs(C.h[i]-priorH)<tol&&C.h[i]<=priorH&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-1])return -1;
  return 0;
}],

// J9: Morning star at VWAP sigma (1σ below/above = dynamic extreme)
// Combines the best of G8 (morning star) and VWAP sigma context
// VWAP+sigma gives a SESSION-SPECIFIC level, not a fixed BB based on rolling history
["J9: Morning star at VWAP sigma", function(C,i){
  if(i<2||C.vwap[i]==null||C.vsd[i]==null||C.atr[i]==null)return 0;
  const sd=C.vsd[i],vw=C.vwap[i];
  if(sd<0.1*C.atr[i])return 0;
  const ms=morningStarDir(C,i);if(!ms)return 0;
  // Morning star below VWAP-1σ = stretched low
  if(ms===1&&C.c[i-1]<vw-0.7*sd)return 1;
  // Evening star above VWAP+1σ = stretched high  
  if(ms===-1&&C.c[i-1]>vw+0.7*sd)return -1;
  return 0;
}],

// J10: I9 but with time filter — NO trades in first 30 min (most noise)
// RTH starts at 9:30 (570 mins). First 30 min = 570-600.
// I9 runs all session. Let's see if filtering out the first 30 min improves quality
["J10: Portfolio G8+S10 post-9:30 only", function(C,i){
  if(C.etMins[i]==null||C.atr[i]==null)return 0;
  const mins=C.etMins[i];
  if(mins<600||mins>=930)return 0; // 10:00am to 3:30pm ET only
  const ms=morningStarDir(C,i);if(ms)return ms;
  if(C.bbU[i]==null||!C.hiVol[i])return 0;
  let nl=true,nh=true;
  for(let q=1;q<=5;q++){if(C.l[i]>=C.l[i-q])nl=false;if(C.h[i]<=C.h[i-q])nh=false;}
  if(nl&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-1]&&C.l[i]<=C.bbL[i]&&C.c[i]>C.bbL[i])return 1;
  if(nh&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-1]&&C.h[i]>=C.bbU[i]&&C.c[i]<C.bbU[i])return -1;
  return 0;
}],

// J11: I9 + RSI2 filter — only take I9 signals when RSI2 confirms extreme
// Adding RSI2 extremeness as a confirming gate on the portfolio:
// If taking a long, RSI2 must be < 30 (short-term oversold)
// If taking a short, RSI2 must be > 70
["J11: Portfolio G8+S10 + RSI2 confirm", function(C,i){
  if(i<5||C.atr[i]==null||C.rsi2[i]==null)return 0;
  const ms=morningStarDir(C,i);
  if(ms===1&&C.rsi2[i]<35)return 1;
  if(ms===-1&&C.rsi2[i]>65)return -1;
  if(C.bbU[i]==null||!C.hiVol[i])return 0;
  let nl=true,nh=true;
  for(let q=1;q<=5;q++){if(C.l[i]>=C.l[i-q])nl=false;if(C.h[i]<=C.h[i-q])nh=false;}
  if(nl&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-1]&&C.l[i]<=C.bbL[i]&&C.c[i]>C.bbL[i]&&C.rsi2[i]<35)return 1;
  if(nh&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-1]&&C.h[i]>=C.bbU[i]&&C.c[i]<C.bbU[i]&&C.rsi2[i]>65)return -1;
  return 0;
}],

// J12: I9 + VWAP side filter — only take I9 in direction of VWAP bias
// The lesson: VWAP tells you which side institutions are playing
// Only take longs when price is below VWAP (cheap, fading toward mean)
// Only take shorts when price is above VWAP (expensive, fading toward mean)
["J12: Portfolio G8+S10 + VWAP side", function(C,i){
  if(i<5||C.atr[i]==null||C.vwap[i]==null)return 0;
  const ms=morningStarDir(C,i);
  if(ms===1&&C.c[i]<=C.vwap[i])return 1;
  if(ms===-1&&C.c[i]>=C.vwap[i])return -1;
  if(C.bbU[i]==null||!C.hiVol[i])return 0;
  let nl=true,nh=true;
  for(let q=1;q<=5;q++){if(C.l[i]>=C.l[i-q])nl=false;if(C.h[i]<=C.h[i-q])nh=false;}
  if(nl&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-1]&&C.l[i]<=C.bbL[i]&&C.c[i]>C.bbL[i]&&C.c[i]<=C.vwap[i])return 1;
  if(nh&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-1]&&C.h[i]>=C.bbU[i]&&C.c[i]<C.bbU[i]&&C.c[i]>=C.vwap[i])return -1;
  return 0;
}],

];

const CONFIGS=[
  {stopMult:1.5,tgtMult:2.0,riskCap:200,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
  {stopMult:1.5,tgtMult:2.5,riskCap:200,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
  {stopMult:1.2,tgtMult:2.0,riskCap:200,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
  {stopMult:1.5,tgtMult:2.0,riskCap:200,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
  {stopMult:1.5,tgtMult:3.0,riskCap:200,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
  {stopMult:1.0,tgtMult:2.0,riskCap:200,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
  {stopMult:1.5,tgtMult:2.0,riskCap:350,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
  {stopMult:1.5,tgtMult:2.5,riskCap:350,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
];

const dol=x=>(x>=0?"+$":"-$")+Math.abs(Math.round(x)).toLocaleString();
const pct=x=>x.toFixed(1)+"%";

(function main(){
  console.log("Gen-6 loading...");
  const allBars=JSON.parse(fs.readFileSync(path.join(__dirname,"data","nq-5m.json"),"utf8"))
    .filter(b=>b&&isFinite(b.c)).sort((a,b)=>a.t-b.t);
  const ET=preET(allBars);
  const daySet=new Set();
  for(let i=0;i<allBars.length;i++)if(ET.rth[i])daySet.add(ET.dk[i]);
  const rthDays=Array.from(daySet).sort();
  const last13=rthDays.slice(-13);
  const cutT=(()=>{for(let i=0;i<allBars.length;i++)if(ET.dk[i]===last13[0])return allBars[i].t;return Infinity;})();
  console.log("13d window: "+last13[0]+" to "+last13[last13.length-1]);
  const C=buildCtx(allBars,ET);
  function run13(fn,p){return sim(allBars,C,ET,(C2,i)=>allBars[i].t>=cutT?fn(C2,i):0,p);}
  function runFull(fn,p){return sim(allBars,C,ET,fn,p);}

  const results=[];
  for(let mi=0;mi<METHODS.length;mi++){
    const name=METHODS[mi][0],fn=METHODS[mi][1];
    process.stdout.write("  "+(mi+1)+"/"+METHODS.length+" "+name+"... ");
    let best13=-Infinity,bestR=null,bestCfg=null;
    for(let ci=0;ci<CONFIGS.length;ci++){
      const p=CONFIGS[ci];
      const r13=run13(fn,p),rF=runFull(fn,p);
      if(r13.net$>best13){
        best13=r13.net$;
        const cp=cPass(rF.trades),m=mc(rF.trades);
        bestR={r13,rF,cp,m};bestCfg=p;
      }
    }
    const tag=bestR.rF.feasible&&bestR.rF.net$>0?" OK":" --";
    console.log("13d "+dol(bestR.r13.net$)+"  full "+dol(bestR.rF.net$)+tag);
    results.push({name,cfg:bestCfg,r13:bestR.r13,rF:bestR.rF,cp:bestR.cp,mc:bestR.m});
  }

  results.sort((a,b)=>{
    const af=a.rF.feasible&&a.rF.net$>0?1:0,bf=b.rF.feasible&&b.rF.net$>0?1:0;
    if(bf!==af)return bf-af;
    return b.r13.net$-a.r13.net$;
  });

  console.log("\n"+"=".repeat(140));
  console.log("  GEN-6 RESULTS — feasible+profitable full-period FIRST");
  console.log("=".repeat(140));
  console.log("Strategy".padEnd(42)+"Config".padEnd(24)+"13d-Net".padStart(10)+"Trd/Win".padStart(11)+"PF".padStart(6)+" | Full-Net".padStart(11)+"Win".padStart(8)+"DD".padStart(10)+"Feas".padStart(6)+"Combine".padStart(10)+"MC%".padStart(7));
  console.log("-".repeat(140));
  for(const r of results){
    const cfg="s"+r.cfg.stopMult+"/t"+r.cfg.tgtMult+" $"+r.cfg.riskCap+" "+r.cfg.maxTr+"/d";
    const star=(r.rF.feasible&&r.rF.net$>0)?"*":" ";
    console.log((star+r.name).slice(0,41).padEnd(42)+cfg.padEnd(24)+
      dol(r.r13.net$).padStart(10)+(r.r13.n+"t "+pct(r.r13.win)).padStart(11)+String(r.r13.pf).padStart(6)+
      " | "+dol(r.rF.net$).padStart(9)+pct(r.rF.win).padStart(8)+("-$"+r.rF.maxDD$).padStart(10)+
      (r.rF.feasible?"YES":"NO ").padStart(6)+(r.cp.passed?"PASS":"FAIL-"+r.cp.why).padStart(10)+(r.mc+"%").padStart(7));
  }

  const good=results.filter(r=>r.rF.feasible&&r.rF.net$>0);
  console.log("\n*** "+good.length+"/"+results.length+" strategies feasible+profitable on full period ***");

  console.log("\nTOP 3 DAY-BY-DAY:");
  for(let ti=0;ti<Math.min(3,results.length);ti++){
    const r=results[ti];
    console.log("\n["+(ti+1)+"] "+r.name);
    console.log("    13d: "+dol(r.r13.net$)+" | "+r.r13.n+"t | "+pct(r.r13.win)+" win | PF "+r.r13.pf+" | DD -$"+r.r13.maxDD$);
    console.log("    Full: "+dol(r.rF.net$)+" | "+r.rF.n+"t | "+pct(r.rF.win)+" | DD -$"+r.rF.maxDD$+" | "+(r.rF.feasible?"FEASIBLE":"BUST"));
    console.log("    Combine: "+(r.cp.passed?"PASS":"FAIL("+r.cp.why+")")+" | MC: "+r.mc+"%");
    if(r.r13.byd&&r.r13.byd.size){
      const s=Array.from(r.r13.byd.entries()).sort((a,b)=>a[0].localeCompare(b[0]));
      for(const[day,pnl]of s)console.log("      "+day+": "+dol(pnl));
    }
  }

  const lines=["# Gen-6 Strategy Battle ("+new Date().toISOString().slice(0,10)+")",
    "","*Asterisk = passes both gates: full net > 0 AND feasible DD/daily.*","",
    "| # | Strategy | Config | 13d Net | Trd | Win | PF | Full Net | Win | DD | Feasible | Combine | MC% |",
    "|---|---|---|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|---:|"];
  for(let ri=0;ri<results.length;ri++){
    const r=results[ri];
    const star=r.rF.feasible&&r.rF.net$>0?"* ":"";
    lines.push("| "+(ri+1)+" | "+star+r.name+" | s"+r.cfg.stopMult+"/t"+r.cfg.tgtMult+" "+r.cfg.maxTr+"/d | "+
      dol(r.r13.net$)+" | "+r.r13.n+" | "+pct(r.r13.win)+" | "+r.r13.pf+" | "+
      dol(r.rF.net$)+" | "+pct(r.rF.win)+" | -$"+r.rF.maxDD$+" | "+(r.rF.feasible?"YES":"NO")+" | "+
      (r.cp.passed?"PASS":"FAIL-"+r.cp.why)+" | "+r.mc+"% |");
  }
  lines.push("","## Top 3 Detail","");
  for(let ti=0;ti<Math.min(3,results.length);ti++){
    const r=results[ti];
    lines.push("### "+(ti+1)+". "+r.name);
    lines.push("- **13d:** "+dol(r.r13.net$)+" | "+r.r13.n+"t | "+pct(r.r13.win)+" win | PF "+r.r13.pf+" | DD -$"+r.r13.maxDD$);
    lines.push("- **Full:** "+dol(r.rF.net$)+" | "+r.rF.n+"t | "+pct(r.rF.win)+" | DD -$"+r.rF.maxDD$+" | "+(r.rF.feasible?"FEASIBLE":"BUST"));
    lines.push("- **Combine:** "+(r.cp.passed?"PASS":"FAIL("+r.cp.why+")")+" | MC: "+r.mc+"%");
    if(r.r13.byd&&r.r13.byd.size){
      lines.push("","| Date | P&L |","|---|---|");
      const s=Array.from(r.r13.byd.entries()).sort((a,b)=>a[0].localeCompare(b[0]));
      for(const[d,p]of s)lines.push("| "+d+" | "+dol(p)+" |");
    }
    lines.push("");
  }
  fs.writeFileSync(path.join(__dirname,"logs","strat-gen6-13d-report.md"),lines.join("\n")+"\n");
  console.log("\nSaved: logs/strat-gen6-13d-report.md");
})();
