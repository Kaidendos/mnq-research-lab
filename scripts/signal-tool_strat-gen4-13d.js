// strat-gen4-13d.js - Generation 4
// Mix: combos of best performers + brand new edges never tried
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
  const ema21=I.ema(c,21),ema50=I.ema(c,50),ema200=I.ema(c,200);
  const atr=I.atr(h,l,c,14),rsi14=I.rsi(c,14),rsi2=I.rsi(c,2);
  const {macdLine,signalLine}=I.macd(c,12,26,9);
  const bb20=I.sma(c,20),bbS=I.stdev(c,20);
  const bbU=bb20.map((v2,i)=>v2==null?null:v2+2*bbS[i]);
  const bbL=bb20.map((v2,i)=>v2==null?null:v2-2*bbS[i]);
  const vol20=I.sma(v,20);

  // Session: VWAP, HOD/LOD, day-open, prior-day HLC, OR
  const vwap=new Array(n).fill(null),vsd=new Array(n).fill(null);
  const hod=new Array(n).fill(null),lod=new Array(n).fill(null),dopen=new Array(n).fill(null);
  const pdH=new Array(n).fill(null),pdL=new Array(n).fill(null),pdC=new Array(n).fill(null);
  const orH=new Array(n).fill(null),orL=new Array(n).fill(null);
  // Intraday swing high/low tracking (for fib & breakout-retest)
  const daySwingH=new Array(n).fill(null),daySwingL=new Array(n).fill(null);
  let vN=0,vD=0,vN2=0,curD=null,hi=-Infinity,lo=Infinity,op=null,oRH=-Infinity,oRL=Infinity;
  const dH=new Map(),dL=new Map(),dC=new Map(),order=[];
  // 5-bar range average (for range expansion)
  const rng5=new Array(n).fill(null);
  for(let i=5;i<n;i++){let s=0;for(let k=i-5;k<i;k++)s+=h[k]-l[k];rng5[i]=s/5;}

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
    daySwingH[i]=hi===-Infinity?null:hi;daySwingL[i]=lo===Infinity?null:lo;
    const prev=order[order.length-1];
    if(prev){pdH[i]=dH.get(prev);pdL[i]=dL.get(prev);pdC[i]=dC.get(prev);}
  }

  // NR7
  const nr7=new Array(n).fill(false);
  for(let i=7;i<n;i++){const rn=h[i]-l[i];let ok=true;for(let k=1;k<7;k++)if(h[i-k]-l[i-k]<=rn)ok=false;nr7[i]=ok;}

  // ET arrays stored in ctx for time-of-day filtering
  const etMins=ET.dm,etRTH=ET.rth;

  return{o,h,l,c,v,n,ema21,ema50,ema200,atr,rsi14,rsi2,macdLine,signalLine,
    bbU,bbL,bb20,vol20,vwap,vsd,hod,lod,dopen,orH,orL,pdH,pdL,pdC,
    daySwingH,daySwingL,rng5,nr7,etMins,etRTH};
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

// H1: COMBO — Morning star AT BB band (G8 + BB level)
// Requires the 3-bar pattern to be happening at a Bollinger extreme
// More selective = higher quality signals
["H1: Morning star @ BB level", function(C,i){
  if(i<2||C.atr[i]==null||C.bbU[i]==null)return 0;
  const a=C.atr[i];
  const bar2body=Math.abs(C.c[i-2]-C.o[i-2]);
  const bar1body=Math.abs(C.c[i-1]-C.o[i-1]);
  const bar0body=Math.abs(C.c[i]-C.o[i]);
  if(bar2body<0.5*a||bar1body>0.4*a||bar0body<0.4*a)return 0;
  // Morning star: big bear, small doji, big bull — AND near lower BB
  if(C.c[i-2]<C.o[i-2]&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-2]&&C.l[i-1]<=C.bbL[i]+0.5*a)return 1;
  // Evening star: big bull, doji, big bear — AND near upper BB
  if(C.c[i-2]>C.o[i-2]&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-2]&&C.h[i-1]>=C.bbU[i]-0.5*a)return -1;
  return 0;
}],

// H2: COMBO — KeyRev@BB + morning star confirmation (2-method AND)
// Needs BOTH a key reversal bar AND the prior bar to be the "doji/star" of the pattern
// Very selective — only fires when multiple patterns align
["H2: KeyRev@BB + star confirm", function(C,i){
  if(i<3||C.bbU[i]==null||C.atr[i]==null)return 0;
  const d=keyRevDir(C,i);if(!d)return 0;
  const a=C.atr[i];
  const priorBody=Math.abs(C.c[i-1]-C.o[i-1]);
  const priorIsSmall=priorBody<0.3*a; // prior bar was a doji/small = star
  if(d===1&&C.l[i]<=C.bbL[i]&&C.c[i]>C.bbL[i]&&priorIsSmall)return 1;
  if(d===-1&&C.h[i]>=C.bbU[i]&&C.c[i]<C.bbU[i]&&priorIsSmall)return -1;
  return 0;
}],

// H3: Fibonacci 50% retracement entry
// Measure the prior session's range (open to HOD or LOD), enter at the 50% fib
// when a reversal bar forms there — a classic institutional entry level
["H3: Fib 50% retracement", function(C,i){
  if(i<1||C.daySwingH[i]==null||C.dopen[i]==null||C.atr[i]==null)return 0;
  const swH=C.daySwingH[i],swL=C.daySwingL[i],rng=swH-swL;
  if(rng<C.atr[i])return 0; // range too small to be meaningful
  const fib50H=swH-0.5*rng; // 50% retrace from high
  const fib50L=swL+0.5*rng; // 50% retrace from low
  const tol=0.2*C.atr[i];
  const d=keyRevDir(C,i);if(!d)return 0;
  // Long: price near 50% fib of the downswing (fib support)
  if(d===1&&Math.abs(C.l[i]-fib50L)<tol)return 1;
  // Short: price near 50% fib of the upswing (fib resistance)
  if(d===-1&&Math.abs(C.h[i]-fib50H)<tol)return -1;
  return 0;
}],

// H4: Engulfing bar at BB band
// A full bullish engulfing (current bar completely swallows prior body)
// happening at the BB lower/upper band — strong reversal signal
["H4: Engulfing bar @ BB", function(C,i){
  if(i<1||C.bbU[i]==null||C.atr[i]==null)return 0;
  const prevBody=[C.o[i-1],C.c[i-1]];
  const prevHi=Math.max(...prevBody),prevLo=Math.min(...prevBody);
  // Bullish engulfing: current bullish bar body engulfs prior bearish body
  const bullEngulf=C.c[i]>C.o[i]&&C.o[i]<prevLo&&C.c[i]>prevHi&&C.c[i-1]<C.o[i-1];
  // Bearish engulfing: current bearish body engulfs prior bullish body
  const bearEngulf=C.c[i]<C.o[i]&&C.o[i]>prevHi&&C.c[i]<prevLo&&C.c[i-1]>C.o[i-1];
  if(bullEngulf&&C.l[i]<=C.bbL[i]+C.atr[i])return 1;
  if(bearEngulf&&C.h[i]>=C.bbU[i]-C.atr[i])return -1;
  return 0;
}],

// H5: MACD zero-line cross + RSI confirmation
// MACD line crosses above zero (momentum shift bullish) + RSI not overbought
// Pure momentum-turning-positive signal at a non-extreme RSI level
["H5: MACD zero cross + RSI", function(C,i){
  if(i<2||C.macdLine[i]==null||C.rsi14[i]==null||C.atr[i]==null)return 0;
  const crossUp=C.macdLine[i-1]<0&&C.macdLine[i]>=0;
  const crossDn=C.macdLine[i-1]>0&&C.macdLine[i]<=0;
  if(crossUp&&C.rsi14[i]<65&&C.rsi14[i]>40)return 1;
  if(crossDn&&C.rsi14[i]>35&&C.rsi14[i]<60)return -1;
  return 0;
}],

// H6: 3-push exhaustion (3 successive extremes each smaller)
// 3 higher highs where each high is LESS than the prior extension = losing momentum
// The crowd keeps pushing but the move is dying — fade it
["H6: 3-push diminishing exhaustion", function(C,i){
  if(i<5||C.atr[i]==null)return 0;
  // Bull exhaustion: 3 higher highs but each extension shrinks
  const hh1=C.h[i-4],hh2=C.h[i-2],hh3=C.h[i]; // peaks spaced 2 bars
  const ext1=hh2-hh1,ext2=hh3-hh2;
  if(hh1<hh2&&hh2<hh3&&ext2<ext1*0.7&&ext2>0){
    // Extensions shrinking + current bar reverses
    if(C.c[i]<C.o[i]&&C.c[i]<C.c[i-1])return -1;
  }
  // Bear exhaustion: 3 lower lows but each extension shrinks
  const ll1=C.l[i-4],ll2=C.l[i-2],ll3=C.l[i];
  const dn1=ll1-ll2,dn2=ll2-ll3;
  if(ll1>ll2&&ll2>ll3&&dn2<dn1*0.7&&dn2>0){
    if(C.c[i]>C.o[i]&&C.c[i]>C.c[i-1])return 1;
  }
  return 0;
}],

// H7: Breakout-retest entry
// Price breaks above/below a prior swing high/low, then pulls back to retest it
// Enter in breakout direction on the retest bounce — "support becomes resistance" flip
["H7: Breakout retest bounce", function(C,i){
  if(i<10||C.atr[i]==null)return 0;
  // Find prior swing high/low from last 10-20 bars (before current bar)
  let swHigh=-Infinity,swLow=Infinity;
  for(let k=i-15;k<i-3;k++){if(k<0)continue;swHigh=Math.max(swHigh,C.h[k]);swLow=Math.min(swLow,C.l[k]);}
  if(swHigh===-Infinity)return 0;
  const tol=0.15*C.atr[i];
  const d=keyRevDir(C,i);if(!d)return 0;
  // Long: prior range broken above (close > swHigh) then pulled back to swHigh and bouncing
  if(d===1&&C.c[i-3]>swHigh&&Math.abs(C.l[i]-swHigh)<tol&&C.c[i]>swHigh)return 1;
  // Short: prior range broken below then pulled back to swLow and rejecting
  if(d===-1&&C.c[i-3]<swLow&&Math.abs(C.h[i]-swLow)<tol&&C.c[i]<swLow)return -1;
  return 0;
}],

// H8: Range expansion fade (today's range > 1.5x 5-day average)
// When today's intraday range is abnormally large, price tends to snap back
// Fade the extreme when a reversal bar forms
["H8: Overextended range fade", function(C,i){
  if(C.rng5[i]==null||C.hod[i]==null||C.atr[i]==null)return 0;
  const todayRng=C.hod[i]-C.lod[i];
  if(todayRng<1.5*C.rng5[i])return 0; // not overextended
  const d=keyRevDir(C,i);if(!d)return 0;
  // Only trade in the direction of mean-reversion (fade the bigger side of the range)
  const midpoint=(C.hod[i]+C.lod[i])/2;
  if(d===1&&C.c[i]<midpoint)return 1;  // price at bottom of big range, bounce
  if(d===-1&&C.c[i]>midpoint)return -1; // price at top of big range, fade
  return 0;
}],

// H9: Power hour momentum (last hour 15:00-16:00 ET = mins 900-960)
// Only enter in the last hour of session when trend is confirmed by VWAP
// Momentum tends to persist into close in trending days
["H9: Power hour momentum (15-16)", function(C,i){
  if(C.etMins[i]==null||C.vwap[i]==null||C.ema200[i]==null||C.atr[i]==null)return 0;
  const mins=C.etMins[i];
  if(mins<900||mins>=960)return 0; // only 15:00-16:00 ET
  // Strong trend: price > VWAP AND > EMA200 = buy momentum
  if(C.c[i]>C.vwap[i]&&C.c[i]>C.ema200[i]&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-1])return 1;
  if(C.c[i]<C.vwap[i]&&C.c[i]<C.ema200[i]&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-1])return -1;
  return 0;
}],

// H10: COMBO — G10 VWAP reclaim + volume spike (best of G10 + volume filter)
// VWAP reclaim was strong (+$2,556 full), add high volume confirmation
// Volume spike on the reclaim bar = institutional participation
["H10: VWAP reclaim + vol spike", function(C,i){
  if(i<2||C.vwap[i]==null||C.ema200[i]==null||C.atr[i]==null||C.vol20[i]==null)return 0;
  const vw=C.vwap[i];
  const highVol=(C.v[i]||0)>1.3*C.vol20[i];
  if(!highVol)return 0;
  if(C.c[i-1]<vw&&C.c[i]>vw&&C.c[i]>C.ema200[i]&&C.c[i]>C.o[i])return 1;
  if(C.c[i-1]>vw&&C.c[i]<vw&&C.c[i]<C.ema200[i]&&C.c[i]<C.o[i])return -1;
  return 0;
}],

// H11: Early session momentum (9:30-10:30 ET) + VWAP direction
// The first hour sets the tone. Trade the dominant direction of the first 12 bars
// when price confirms by holding above/below VWAP
["H11: First-hour momentum", function(C,i){
  if(C.etMins[i]==null||C.vwap[i]==null||C.atr[i]==null)return 0;
  const mins=C.etMins[i];
  if(mins<600||mins>=660)return 0; // only 10:00-11:00 ET (after first 30m)
  if(C.dopen[i]==null)return 0;
  // First-hour momentum: close significantly above/below open
  const morningMove=C.c[i]-C.dopen[i];
  if(morningMove>C.atr[i]&&C.c[i]>C.vwap[i]&&C.c[i]>C.o[i])return 1;
  if(morningMove<-C.atr[i]&&C.c[i]<C.vwap[i]&&C.c[i]<C.o[i])return -1;
  return 0;
}],

// H12: Inside-bar momentum break
// A bar that trades entirely within the prior bar's range (inside bar = compression)
// then the NEXT bar breaks out in a direction with VWAP confirming → ride it
["H12: Inside-bar breakout", function(C,i){
  if(i<2||C.vwap[i]==null||C.atr[i]==null)return 0;
  // Prior bar is an inside bar (fully within bar before it)
  const isInside=C.h[i-1]<=C.h[i-2]&&C.l[i-1]>=C.l[i-2];
  if(!isInside)return 0;
  // Current bar breaks out of the inside bar range
  const breakUp=C.c[i]>C.h[i-1]&&C.c[i]>C.vwap[i];
  const breakDn=C.c[i]<C.l[i-1]&&C.c[i]<C.vwap[i];
  if(breakUp&&C.c[i]>C.o[i])return 1;
  if(breakDn&&C.c[i]<C.o[i])return -1;
  return 0;
}],

];

const CONFIGS=[
  {stopMult:1.5,tgtMult:2.0,riskCap:200,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
  {stopMult:1.5,tgtMult:2.5,riskCap:200,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
  {stopMult:1.2,tgtMult:2.0,riskCap:200,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
  {stopMult:1.5,tgtMult:2.0,riskCap:200,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
  {stopMult:1.5,tgtMult:3.0,riskCap:200,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
  {stopMult:1.0,tgtMult:2.0,riskCap:200,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
];

const dol=x=>(x>=0?"+$":"-$")+Math.abs(Math.round(x)).toLocaleString();
const pct=x=>x.toFixed(1)+"%";

(function main(){
  console.log("Gen-4 loading...");
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
      const p=CONFIGS[ci],r13=run13(fn,p),rF=runFull(fn,p);
      if(r13.net$>best13){best13=r13.net$;const cp=cPass(rF.trades),m=mc(rF.trades);bestR={r13,rF,cp,m};bestCfg=p;}
    }
    console.log("13d "+dol(bestR.r13.net$)+"  full "+dol(bestR.rF.net$));
    results.push({name,cfg:bestCfg,r13:bestR.r13,rF:bestR.rF,cp:bestR.cp,mc:bestR.m});
  }
  results.sort((a,b)=>b.r13.net$-a.r13.net$);

  console.log("\n"+"=".repeat(130));
  console.log("  GEN-4 STRATEGY BATTLE - 13-DAY WINDOW");
  console.log("=".repeat(130));
  console.log("Strategy".padEnd(36)+"Config".padEnd(22)+"13d-Net".padStart(10)+"Trd/Win".padStart(11)+"PF".padStart(6)+" | Full-Net".padStart(11)+"Win".padStart(8)+"DD".padStart(10)+"Feas".padStart(6)+"Combine".padStart(10)+"MC%".padStart(7));
  console.log("-".repeat(130));
  for(const r of results){
    const cfg="s"+r.cfg.stopMult+"/t"+r.cfg.tgtMult+" $"+r.cfg.riskCap+" "+r.cfg.maxTr+"/d";
    console.log(r.name.slice(0,35).padEnd(36)+cfg.padEnd(22)+
      dol(r.r13.net$).padStart(10)+(r.r13.n+"t "+pct(r.r13.win)).padStart(11)+String(r.r13.pf).padStart(6)+
      " | "+dol(r.rF.net$).padStart(9)+pct(r.rF.win).padStart(8)+("-$"+r.rF.maxDD$).padStart(10)+
      (r.rF.feasible?"YES":"NO ").padStart(6)+(r.cp.passed?"PASS":"FAIL-"+r.cp.why).padStart(10)+(r.mc+"%").padStart(7));
  }

  console.log("\n TOP 3 DAY-BY-DAY:");
  for(let ti=0;ti<Math.min(3,results.length);ti++){
    const r=results[ti];
    console.log("\n["+(ti+1)+"] "+r.name+" | s"+r.cfg.stopMult+"/t"+r.cfg.tgtMult+" $"+r.cfg.riskCap+" "+r.cfg.maxTr+"/d "+r.cfg.dayStop);
    console.log("    13d: "+dol(r.r13.net$)+" | "+r.r13.n+"t | "+pct(r.r13.win)+" win | PF "+r.r13.pf+" | DD -$"+r.r13.maxDD$);
    console.log("    Full: "+dol(r.rF.net$)+" | "+r.rF.n+"t | "+pct(r.rF.win)+" | DD -$"+r.rF.maxDD$+" | "+(r.rF.feasible?"FEASIBLE":"NOT FEASIBLE"));
    console.log("    Combine: "+(r.cp.passed?"PASS":"FAIL("+r.cp.why+")")+" | MC: "+r.mc+"%");
    if(r.r13.byd&&r.r13.byd.size){
      const s=Array.from(r.r13.byd.entries()).sort((a,b)=>a[0].localeCompare(b[0]));
      for(const[day,pnl]of s)console.log("      "+day+": "+dol(pnl));
    }
  }

  // markdown
  const lines=["# Gen-4 Strategy Battle - 13d ("+new Date().toISOString().slice(0,10)+")","",
    "Combos of best performers + brand-new edges. Same risk model throughout.","",
    "| # | Strategy | Config | 13d Net | Trd | Win | PF | Full Net | Full Win | DD | Feasible | Combine | MC% |",
    "|---|---|---|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|---:|"];
  for(let ri=0;ri<results.length;ri++){
    const r=results[ri];
    lines.push("| "+(ri+1)+" | "+r.name+" | s"+r.cfg.stopMult+"/t"+r.cfg.tgtMult+" "+r.cfg.maxTr+"/d | "+
      dol(r.r13.net$)+" | "+r.r13.n+" | "+pct(r.r13.win)+" | "+r.r13.pf+" | "+
      dol(r.rF.net$)+" | "+pct(r.rF.win)+" | -$"+r.rF.maxDD$+" | "+(r.rF.feasible?"YES":"NO")+" | "+
      (r.cp.passed?"PASS":"FAIL-"+r.cp.why)+" | "+r.mc+"% |");
  }
  lines.push("","## Top 3 Day-by-Day","");
  for(let ti=0;ti<Math.min(3,results.length);ti++){
    const r=results[ti];
    lines.push("### "+(ti+1)+". "+r.name);
    lines.push("- **13d:** "+dol(r.r13.net$)+" | "+r.r13.n+"t | "+pct(r.r13.win)+" win | PF "+r.r13.pf+" | DD -$"+r.r13.maxDD$);
    lines.push("- **Full:** "+dol(r.rF.net$)+" | "+r.rF.n+"t | "+pct(r.rF.win)+" | DD -$"+r.rF.maxDD$+" | "+(r.rF.feasible?"FEASIBLE":"NOT FEASIBLE"));
    lines.push("- **Combine:** "+(r.cp.passed?"PASS":"FAIL("+r.cp.why+")")+" | MC: "+r.mc+"%");
    if(r.r13.byd&&r.r13.byd.size){
      lines.push("","| Date | P&L |","|---|---|");
      const s=Array.from(r.r13.byd.entries()).sort((a,b)=>a[0].localeCompare(b[0]));
      for(const[d,p]of s)lines.push("| "+d+" | "+dol(p)+" |");
    }
    lines.push("");
  }
  fs.writeFileSync(path.join(__dirname,"logs","strat-gen4-13d-report.md"),lines.join("\n")+"\n");
  console.log("\nSaved: logs/strat-gen4-13d-report.md");
})();
