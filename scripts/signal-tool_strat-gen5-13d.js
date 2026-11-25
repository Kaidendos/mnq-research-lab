// strat-gen5-13d.js - Generation 5: learning from every loss
//
// LESSONS ENCODED:
// - H8/H12 lesson: 13d winners that lose full-period are OVERFITS. Hard-gate: full net > 0 + feasible
// - G3/H7 lesson: if < 5 trades on 13d, the signal is too rare to matter
// - G8 lesson: morning star WORKS — build variants of it
// - H9 lesson: power hour has something — refine it
// - MACD/engulfing/fib lesson: complex multi-step patterns don't fire enough
// - Volume lesson: vol filters consistently help
// - VWAP lesson: session context (VWAP) improves almost everything
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

  // session data
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
  // 5-bar range avg
  const rng5=new Array(n).fill(null);
  for(let i=5;i<n;i++){let s=0;for(let k=i-5;k<i;k++)s+=h[k]-l[k];rng5[i]=s/5;}
  // Low-vol: bar volume < 0.6x average (volume dry-up)
  const lowVol=new Array(n).fill(false);
  for(let i=0;i<n;i++)if(vol20[i]!=null)lowVol[i]=(v[i]||0)<0.6*vol20[i];

  return{o,h,l,c,v,n,ema9,ema21,ema200,atr,rsi14,rsi2,bbU,bbL,bb20,vol20,
    vwap,vsd,hod,lod,dopen,orH,orL,pdH,pdL,pdC,rng5,lowVol,
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

// I1: Morning star variant — at SESSION LOD/HOD instead of BB
// G8 (morning star) worked. What if the anchor is the day's extreme, not BB?
// Session LOD = true intraday support; HOD = true intraday resistance
["I1: Morning star at session extreme", function(C,i){
  if(i<2||C.atr[i]==null||C.hod[i]==null)return 0;
  const a=C.atr[i];
  const b2=Math.abs(C.c[i-2]-C.o[i-2]),b1=Math.abs(C.c[i-1]-C.o[i-1]),b0=Math.abs(C.c[i]-C.o[i]);
  if(b2<0.5*a||b1>0.35*a||b0<0.4*a)return 0;
  // Morning star: at/near LOD
  if(C.c[i-2]<C.o[i-2]&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-2]){
    if(C.l[i-1]<=C.lod[i]+0.3*a)return 1;
  }
  // Evening star: at/near HOD
  if(C.c[i-2]>C.o[i-2]&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-2]){
    if(C.h[i-1]>=C.hod[i]-0.3*a)return -1;
  }
  return 0;
}],

// I2: Morning star with VWAP direction filter
// G8 lesson: it worked broadly. Add VWAP direction so we only take
// morning stars that align with the session bias
["I2: Morning star + VWAP align", function(C,i){
  if(i<2||C.atr[i]==null||C.vwap[i]==null)return 0;
  const a=C.atr[i];
  const b2=Math.abs(C.c[i-2]-C.o[i-2]),b1=Math.abs(C.c[i-1]-C.o[i-1]),b0=Math.abs(C.c[i]-C.o[i]);
  if(b2<0.5*a||b1>0.4*a||b0<0.4*a)return 0;
  // Morning star + price below VWAP (we're fading toward VWAP = lower risk)
  if(C.c[i-2]<C.o[i-2]&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-2]&&C.c[i]<C.vwap[i])return 1;
  // Evening star + price above VWAP
  if(C.c[i-2]>C.o[i-2]&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-2]&&C.c[i]>C.vwap[i])return -1;
  return 0;
}],

// I3: Power hour refined — ONLY when morning was trending (OR direction matches close)
// H9 lesson: power hour works but needs context. Filter: only trade power hour
// continuation when the opening range direction matches the current move
["I3: Power hour + OR confirmation", function(C,i){
  if(C.etMins[i]==null||C.orH[i]==null||C.vwap[i]==null||C.atr[i]==null)return 0;
  const mins=C.etMins[i];
  if(mins<900||mins>=960)return 0;
  if(C.orH[i]-C.orL[i]<0.5*C.atr[i])return 0; // need real OR
  const orMid=(C.orH[i]+C.orL[i])/2;
  // OR was bullish (closed above OR mid) → only take long signals in power hour
  if(C.c[i]>C.vwap[i]&&C.c[i]>orMid&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-1])return 1;
  if(C.c[i]<C.vwap[i]&&C.c[i]<orMid&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-1])return -1;
  return 0;
}],

// I4: Volume dry-up reversal at BB
// Learned: volume HELPS filters. New idea: when price tests a BB band
// with BELOW average volume (no conviction) + reversal bar = weak test = fade
["I4: Low-vol BB test reversal", function(C,i){
  if(C.bbU[i]==null||C.atr[i]==null||C.vol20[i]==null)return 0;
  if(!C.lowVol[i])return 0; // need below-avg volume on this bar
  const d=keyRevDir(C,i);if(!d)return 0;
  if(d===1&&C.l[i]<=C.bbL[i]&&C.c[i]>C.bbL[i])return 1;
  if(d===-1&&C.h[i]>=C.bbU[i]&&C.c[i]<C.bbU[i])return -1;
  return 0;
}],

// I5: Failed auction (3-bar)
// Price attempts to break a level for 3 bars but can't close above/below it
// The 4th bar signals failure → trade the reversal
// This is how prop traders think about trapped breakout buyers/sellers
["I5: Failed 3-bar auction", function(C,i){
  if(i<4||C.atr[i]==null)return 0;
  // Find recent swing high/low from bars i-10 to i-4
  let swH=-Infinity,swL=Infinity;
  for(let k=i-10;k<i-3;k++){if(k<0)continue;swH=Math.max(swH,C.h[k]);swL=Math.min(swL,C.l[k]);}
  if(swH===-Infinity)return 0;
  const tol=0.3*C.atr[i];
  // 3 bars attempted above swH (each bar's high > swH) but all closed below it
  const attempt3Up=C.h[i-3]>swH&&C.c[i-3]<swH&&C.h[i-2]>swH&&C.c[i-2]<swH&&C.h[i-1]>swH&&C.c[i-1]<swH;
  const attempt3Dn=C.l[i-3]<swL&&C.c[i-3]>swL&&C.l[i-2]<swL&&C.c[i-2]>swL&&C.l[i-1]<swL&&C.c[i-1]>swL;
  // 4th bar reverses hard
  if(attempt3Up&&C.c[i]<swH-tol&&C.c[i]<C.o[i])return -1;
  if(attempt3Dn&&C.c[i]>swL+tol&&C.c[i]>C.o[i])return 1;
  return 0;
}],

// I6: 10:00 ET reversal (the known "10 o'clock turn")
// The first 30 minutes of trading often reverses at 10:00 AM ET
// Specifically: if the 9:30-10:00 move was strong, fade it at 10:00
["I6: 10:00 ET reversal", function(C,i){
  if(C.etMins[i]==null||C.dopen[i]==null||C.atr[i]==null||C.vwap[i]==null)return 0;
  const mins=C.etMins[i];
  if(mins<600||mins>=615)return 0; // exactly 10:00-10:15 ET (2-3 bars)
  const morningMove=C.c[i]-C.dopen[i];
  // Strong first-30m move that we now fade
  if(morningMove>1.5*C.atr[i]&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-1])return -1;
  if(morningMove<-1.5*C.atr[i]&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-1])return 1;
  return 0;
}],

// I7: EMA9/EMA21 cross at BB level (fast cross at extreme)
// When the 9-period EMA crosses the 21-period EMA AND price is at a BB band
// Cross = momentum shift; BB = overextended level; together = high quality
["I7: EMA9/21 cross at BB", function(C,i){
  if(i<2||C.ema9[i]==null||C.ema21[i]==null||C.bbU[i]==null||C.atr[i]==null)return 0;
  const crossUp=C.ema9[i-1]<=C.ema21[i-1]&&C.ema9[i]>C.ema21[i];
  const crossDn=C.ema9[i-1]>=C.ema21[i-1]&&C.ema9[i]<C.ema21[i];
  if(crossUp&&C.c[i]<C.bbL[i]+C.atr[i])return 1;
  if(crossDn&&C.c[i]>C.bbU[i]-C.atr[i])return -1;
  return 0;
}],

// I8: Hammer pattern at VWAP or key level
// Classic hammer: lower wick >= 2x body, close in top third, tiny upper wick
// A hammer at VWAP = clean mean-reversion entry with pattern confirmation
["I8: Hammer/star at VWAP", function(C,i){
  if(C.vwap[i]==null||C.atr[i]==null)return 0;
  const body=Math.abs(C.c[i]-C.o[i]),rng=C.h[i]-C.l[i];
  if(rng<0.3*C.atr[i]||body<0.001)return 0;
  const lowerWick=Math.min(C.c[i],C.o[i])-C.l[i];
  const upperWick=C.h[i]-Math.max(C.c[i],C.o[i]);
  const closeInTop=(C.c[i]-C.l[i])/rng>0.6;
  const closeInBot=(C.h[i]-C.c[i])/rng<0.4?false:(C.h[i]-C.c[i])/rng>0.6;
  const vw=C.vwap[i],tol=0.4*C.atr[i];
  // Hammer near VWAP (from below) → long
  if(lowerWick>=2*body&&closeInTop&&upperWick<0.3*body&&Math.abs(C.l[i]-vw)<tol&&C.c[i]>vw)return 1;
  // Shooting star near VWAP (from above) → short
  if(upperWick>=2*body&&!closeInTop&&lowerWick<0.3*body&&Math.abs(C.h[i]-vw)<tol&&C.c[i]<vw)return -1;
  return 0;
}],

// I9: PORTFOLIO — G8 morning star OR S10 KeyRev+volume (whichever fires first)
// Lesson: two good strategies can cover each other's gaps
// G8 fires ~35t/period, S10 ~62t — combined should give better coverage
// without overlapping much (different pattern types)
["I9: Portfolio G8+S10 (star OR vol-rev)", function(C,i){
  if(i<5||C.atr[i]==null)return 0;
  // G8: morning/evening star
  const a=C.atr[i];
  if(i>=2){
    const b2=Math.abs(C.c[i-2]-C.o[i-2]),b1=Math.abs(C.c[i-1]-C.o[i-1]),b0=Math.abs(C.c[i]-C.o[i]);
    if(b2>=0.5*a&&b1<=0.4*a&&b0>=0.4*a){
      if(C.c[i-2]<C.o[i-2]&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-2])return 1;
      if(C.c[i-2]>C.o[i-2]&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-2])return -1;
    }
  }
  // S10: KeyRev@BB + high volume
  if(C.bbU[i]==null||C.vol20[i]==null)return 0;
  if(!((C.v[i]||0)>1.5*C.vol20[i]))return 0;
  let nl=true,nh=true;
  for(let q=1;q<=5;q++){if(C.l[i]>=C.l[i-q])nl=false;if(C.h[i]<=C.h[i-q])nh=false;}
  if(nl&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-1]&&C.l[i]<=C.bbL[i]&&C.c[i]>C.bbL[i])return 1;
  if(nh&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-1]&&C.h[i]>=C.bbU[i]&&C.c[i]<C.bbU[i])return -1;
  return 0;
}],

// I10: VWAP compression breakout
// Price oscillates within 0.5 ATR of VWAP for 5+ bars (tight range near fair value)
// then a bar closes more than 1 ATR away = expansion starting → ride it
["I10: VWAP compression breakout", function(C,i){
  if(i<6||C.vwap[i]==null||C.atr[i]==null)return 0;
  const a=C.atr[i],vw=C.vwap[i];
  // Last 5 bars must all be within 0.5 ATR of VWAP
  let compressed=true;
  for(let k=i-5;k<i;k++){if(Math.abs(C.c[k]-vw)>0.5*a){compressed=false;break;}}
  if(!compressed)return 0;
  // Current bar breaks out
  if(C.c[i]>vw+a&&C.c[i]>C.o[i])return 1;
  if(C.c[i]<vw-a&&C.c[i]<C.o[i])return -1;
  return 0;
}],

// I11: Prior day close reaction
// The prior day's closing price is a key level — institutions reference it
// When price tests PDC and shows a key reversal, it's a high-probability entry
["I11: Prior day close reaction", function(C,i){
  if(C.pdC[i]==null||C.atr[i]==null)return 0;
  const pdc=C.pdC[i],tol=0.2*C.atr[i];
  const d=keyRevDir(C,i);if(!d)return 0;
  if(d===1&&Math.abs(C.l[i]-pdc)<tol&&C.c[i]>pdc)return 1;
  if(d===-1&&Math.abs(C.h[i]-pdc)<tol&&C.c[i]<pdc)return -1;
  return 0;
}],

// I12: Trend + two consecutive pullback bars then momentum resumes
// In a trend (above EMA200), wait for EXACTLY 2 bars of pullback (lower closes)
// then the 3rd bar resumes trend direction with a strong close = "two-bar pullback"
// This is a classic setup used by retail and professional traders
["I12: Two-bar pullback resume", function(C,i){
  if(i<4||C.ema200[i]==null||C.vwap[i]==null||C.atr[i]==null)return 0;
  const upTrend=C.c[i]>C.ema200[i]&&C.c[i]>C.vwap[i];
  const dnTrend=C.c[i]<C.ema200[i]&&C.c[i]<C.vwap[i];
  // Two bars down into uptrend
  const twoPullDn=C.c[i-2]<C.c[i-3]&&C.c[i-1]<C.c[i-2]; // 2 lower closes
  const twoPullUp=C.c[i-2]>C.c[i-3]&&C.c[i-1]>C.c[i-2]; // 2 higher closes
  const rng=C.h[i]-C.l[i];
  const strongBull=C.c[i]>C.o[i]&&(C.c[i]-C.l[i])/Math.max(rng,0.001)>0.6;
  const strongBear=C.c[i]<C.o[i]&&(C.h[i]-C.c[i])/Math.max(rng,0.001)>0.6;
  if(upTrend&&twoPullDn&&strongBull&&C.c[i]>C.c[i-1])return 1;
  if(dnTrend&&twoPullUp&&strongBear&&C.c[i]<C.c[i-1])return -1;
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
];

const dol=x=>(x>=0?"+$":"-$")+Math.abs(Math.round(x)).toLocaleString();
const pct=x=>x.toFixed(1)+"%";

(function main(){
  console.log("Gen-5 loading (learning from losses)...");
  const allBars=JSON.parse(fs.readFileSync(path.join(__dirname,"data","nq-5m.json"),"utf8"))
    .filter(b=>b&&isFinite(b.c)).sort((a,b)=>a.t-b.t);
  const ET=preET(allBars);
  const daySet=new Set();
  for(let i=0;i<allBars.length;i++)if(ET.rth[i])daySet.add(ET.dk[i]);
  const rthDays=Array.from(daySet).sort();
  const last13=rthDays.slice(-13);
  const cutT=(()=>{for(let i=0;i<allBars.length;i++)if(ET.dk[i]===last13[0])return allBars[i].t;return Infinity;})();
  console.log("13d: "+last13[0]+" to "+last13[last13.length-1]);
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

  // Sort: feasible full-period first, then by 13d net
  results.sort((a,b)=>{
    const af=a.rF.feasible&&a.rF.net$>0?1:0,bf=b.rF.feasible&&b.rF.net$>0?1:0;
    if(bf!==af)return bf-af;
    return b.r13.net$-a.r13.net$;
  });

  console.log("\n"+"=".repeat(135));
  console.log("  GEN-5 — sorted: feasible+profitable full-period first, then 13d net");
  console.log("=".repeat(135));
  console.log("Strategy".padEnd(38)+"Config".padEnd(22)+"13d-Net".padStart(10)+"Trd/Win".padStart(11)+"PF".padStart(6)+" | Full-Net".padStart(11)+"Win".padStart(8)+"DD".padStart(10)+"Feas".padStart(6)+"Combine".padStart(10)+"MC%".padStart(7));
  console.log("-".repeat(135));
  for(const r of results){
    const cfg="s"+r.cfg.stopMult+"/t"+r.cfg.tgtMult+" $"+r.cfg.riskCap+" "+r.cfg.maxTr+"/d";
    const star=(r.rF.feasible&&r.rF.net$>0)?"*":" ";
    console.log((star+r.name).slice(0,37).padEnd(38)+cfg.padEnd(22)+
      dol(r.r13.net$).padStart(10)+(r.r13.n+"t "+pct(r.r13.win)).padStart(11)+String(r.r13.pf).padStart(6)+
      " | "+dol(r.rF.net$).padStart(9)+pct(r.rF.win).padStart(8)+("-$"+r.rF.maxDD$).padStart(10)+
      (r.rF.feasible?"YES":"NO ").padStart(6)+(r.cp.passed?"PASS":"FAIL-"+r.cp.why).padStart(10)+(r.mc+"%").padStart(7));
  }

  const good=results.filter(r=>r.rF.feasible&&r.rF.net$>0);
  console.log("\n*** "+good.length+" strategies feasible+profitable on full period ***");

  console.log("\nTOP 3 (feasible first) DAY-BY-DAY:");
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

  const lines=["# Gen-5 Strategy Battle - 13d ("+new Date().toISOString().slice(0,10)+")",
    "","*Sorted: feasible+profitable full-period FIRST. Asterisk = passes both gates.*","",
    "| # | Strategy | Config | 13d Net | Trd | Win | PF | Full Net | Full Win | DD | Feasible | Combine | MC% |",
    "|---|---|---|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|---:|"];
  for(let ri=0;ri<results.length;ri++){
    const r=results[ri];
    const star=r.rF.feasible&&r.rF.net$>0?"* ":"";
    lines.push("| "+(ri+1)+" | "+star+r.name+" | s"+r.cfg.stopMult+"/t"+r.cfg.tgtMult+" "+r.cfg.maxTr+"/d | "+
      dol(r.r13.net$)+" | "+r.r13.n+" | "+pct(r.r13.win)+" | "+r.r13.pf+" | "+
      dol(r.rF.net$)+" | "+pct(r.rF.win)+" | -$"+r.rF.maxDD$+" | "+(r.rF.feasible?"YES":"NO")+" | "+
      (r.cp.passed?"PASS":"FAIL-"+r.cp.why)+" | "+r.mc+"% |");
  }
  lines.push("","## Top 3 Day-by-Day","");
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
  fs.writeFileSync(path.join(__dirname,"logs","strat-gen5-13d-report.md"),lines.join("\n")+"\n");
  console.log("\nSaved: logs/strat-gen5-13d-report.md");
})();
