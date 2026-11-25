// strat-gen3-13d.js - Generation 3: genuinely new entry edges
// Same battle-hardened risk model. 10 totally different trade ideas.
// Run: node strat-gen3-13d.js
"use strict";
const fs   = require("fs");
const path = require("path");
require("./public/indicators.js");
const I = globalThis.Indicators;

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
  const bb20=I.sma(c,20),bbS=I.stdev(c,20);
  const bbU=bb20.map((v2,i)=>v2==null?null:v2+2*bbS[i]);
  const bbL=bb20.map((v2,i)=>v2==null?null:v2-2*bbS[i]);

  // Session stats: VWAP, HOD, LOD, day-open, prior-day H/L/C
  const vwap=new Array(n).fill(null),vsd=new Array(n).fill(null);
  const hod=new Array(n).fill(null),lod=new Array(n).fill(null),dopen=new Array(n).fill(null);
  const pdH=new Array(n).fill(null),pdL=new Array(n).fill(null),pdC=new Array(n).fill(null);
  const orH=new Array(n).fill(null),orL=new Array(n).fill(null);
  let vN=0,vD=0,vN2=0,hi=-Inf,lo=Inf,op=null,curD=null;
  let oRH=-Inf,oRL=Inf;
  const dH=new Map(),dL=new Map(),dC=new Map(),order=[];
  for(let i=0;i<n;i++){
    const dk=ET.dk[i],inR=ET.rth[i],mins=ET.dm[i],dow=ET.dw[i];
    if(dk!==curD){
      if(curD){dH.set(curD,hi);dL.set(curD,lo);dC.set(curD,c[i-1]);order.push(curD);}
      vN=vD=vN2=0;hi=-Inf;lo=Inf;op=null;oRH=-Inf;oRL=Inf;curD=dk;
    }
    if(inR){
      if(op==null)op=o[i];
      hi=Math.max(hi,h[i]);lo=Math.min(lo,l[i]);
      const hlc3=(h[i]+l[i]+c[i])/3,vol=v[i]||1;
      vN+=hlc3*vol;vN2+=hlc3*hlc3*vol;vD+=vol;
      if(vD>0){const m=vN/vD;vwap[i]=m;vsd[i]=Math.sqrt(Math.max(0,vN2/vD-m*m));}
      if(dow>=1&&dow<=5&&mins>=RTH_S&&mins<RTH_S+30){oRH=Math.max(oRH,h[i]);oRL=Math.min(oRL,l[i]);}
    }
    hod[i]=hi===-Inf?null:hi;lod[i]=lo===Inf?null:lo;dopen[i]=op;
    orH[i]=oRH===-Inf?null:oRH;orL[i]=oRL===Inf?null:oRL;
    const prev=order[order.length-1];
    if(prev){pdH[i]=dH.get(prev);pdL[i]=dL.get(prev);pdC[i]=dC.get(prev);}
  }
  // ATR 20-bar average for volatility regime
  const atr20=I.sma(atr.map(x=>x==null?0:x),20);
  // Volume 20-bar avg
  const vol20=I.sma(v,20);
  // NR4/NR7: narrowest range in 4/7 bars
  const nr4=new Array(n).fill(false),nr7=new Array(n).fill(false);
  for(let i=7;i<n;i++){
    const rng=h[i]-l[i];
    let n4=true,n7=true;
    for(let k=1;k<4;k++)if(h[i-k]-l[i-k]<=rng)n4=false;
    for(let k=1;k<7;k++)if(h[i-k]-l[i-k]<=rng)n7=false;
    nr4[i]=n4;nr7[i]=n7;
  }
  const Inf2=Infinity;
  return{o,h,l,c,v,n,ema21,ema50,ema200,atr,atr20,rsi14,rsi2,bbU,bbL,bb20,
    vwap,vsd,hod,lod,dopen,orH,orL,pdH,pdL,pdC,nr4,nr7,vol20};
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
    cum+=t.pnl;pk=Math.max(pk,cum);
    bd.set(t.day,(bd.get(t.day)||0)+t.pnl);
    if(pk-cum>=MLL)return{passed:false,why:"MLL"};
    if(bd.get(t.day)<=-DLL)return{passed:false,why:"DLL"};
    if(cum>=TARGET)return{passed:true,why:"target"};
  }
  return{passed:false,why:"no-target"};
}
function mc(trades,iters){
  iters=iters||2000;if(!trades.length)return 0;
  const p=trades.map(t=>t.pnl);let pass=0;
  for(let it=0;it<iters;it++){
    for(let k=p.length-1;k>0;k--){const j=(Math.random()*(k+1))|0;const t=p[k];p[k]=p[j];p[j]=t;}
    let cum=0,pk=0,ok=false,dead=false;
    for(let k=0;k<p.length;k++){cum+=p[k];pk=Math.max(pk,cum);if(pk-cum>=MLL){dead=true;break;}if(cum>=TARGET){ok=true;break;}}
    if(ok&&!dead)pass++;
  }
  return+(pass/iters*100).toFixed(1);
}

// ============================================================
//  THE NEW STRATEGIES
// ============================================================
const METHODS=[

// G1: Gap fade — open gaps away from prev close by >0.5 ATR, fade it back
// Logic: large gaps tend to partially fill, especially in index futures
["G1: Gap fade (>0.5 ATR)", function(C,i){
  if(C.pdC[i]==null||C.atr[i]==null||C.dopen[i]==null)return 0;
  // Only fire in first 30 min (within 6 bars of RTH open = mins 570-600)
  // Check gap at first bar of day (dopen just set = same as open[i])
  if(C.dopen[i]!==C.o[i])return 0; // not first bar
  const gap=C.o[i]-C.pdC[i];
  if(Math.abs(gap)<0.5*C.atr[i])return 0;
  // Fade: gap up → short, gap down → long
  return gap>0?-1:1;
}],

// G2: Session HOD/LOD test-and-reverse
// When price makes a new session high/low and then the NEXT bar reverses hard
// (closes back below/above the prior bar's midpoint), fade the extreme
["G2: HOD/LOD test-reverse", function(C,i){
  if(i<2)return 0;
  if(C.hod[i]==null||C.atr[i]==null)return 0;
  const prevMid=(C.h[i-1]+C.l[i-1])/2;
  // New HOD on prior bar, current bar closes below prior bar's mid → bear fade
  const newHOD=C.h[i-1]>=C.hod[i-2]; // prior bar set a new HOD
  const newLOD=C.l[i-1]<=C.lod[i-2];
  if(newHOD&&C.c[i]<prevMid&&C.c[i]<C.o[i])return -1;
  if(newLOD&&C.c[i]>prevMid&&C.c[i]>C.o[i])return  1;
  return 0;
}],

// G3: RSI14 divergence
// Price makes new 10-bar low but RSI14 is higher than it was at the prior low → bull divergence
// Price makes new 10-bar high but RSI14 is lower → bear divergence
["G3: RSI14 divergence", function(C,i){
  if(i<20)return 0;
  if(C.rsi14[i]==null||C.atr[i]==null)return 0;
  // Find prior 10-bar low/high
  let priorLowIdx=-1,priorHighIdx=-1;
  for(let k=i-2;k>=i-15;k--){
    if(priorLowIdx<0&&C.l[k]<C.l[i-1])priorLowIdx=k;
    if(priorHighIdx<0&&C.h[k]>C.h[i-1])priorHighIdx=k;
  }
  // Bull div: new low on price, RSI higher than prior low's RSI
  if(priorLowIdx>0&&C.l[i-1]<C.l[priorLowIdx]&&C.rsi14[i-1]>C.rsi14[priorLowIdx]){
    // Confirm: current bar is bullish
    if(C.c[i]>C.o[i]&&C.c[i]>C.c[i-1])return 1;
  }
  // Bear div: new high on price, RSI lower
  if(priorHighIdx>0&&C.h[i-1]>C.h[priorHighIdx]&&C.rsi14[i-1]<C.rsi14[priorHighIdx]){
    if(C.c[i]<C.o[i]&&C.c[i]<C.c[i-1])return -1;
  }
  return 0;
}],

// G4: Big-bar exhaustion fade (ATR spike)
// When a single bar's range is >2x the 14-bar ATR, the move is overextended
// Fade: enter in opposite direction on the NEXT bar open
["G4: ATR spike exhaustion", function(C,i){
  if(i<2||C.atr[i-1]==null)return 0;
  const rng=C.h[i-1]-C.l[i-1];
  if(rng<2*C.atr[i-1])return 0; // not a spike
  // Direction of the spike bar
  const spikeDir=C.c[i-1]>C.o[i-1]?1:-1;
  // Confirm reversal: current bar moves opposite
  if(spikeDir===1&&C.c[i]<C.o[i])return -1;
  if(spikeDir===-1&&C.c[i]>C.o[i])return  1;
  return 0;
}],

// G5: Prior-day high/low test + rejection
// Price pokes through prior day's H or L then closes back inside → trapped breakout
["G5: Prior-day level rejection", function(C,i){
  if(i<1)return 0;
  if(C.pdH[i]==null||C.atr[i]==null)return 0;
  // Bull: wick below pdL, close above pdL, bullish bar
  if(C.l[i]<C.pdL[i]&&C.c[i]>C.pdL[i]&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-1])return  1;
  // Bear: wick above pdH, close below pdH, bearish bar
  if(C.h[i]>C.pdH[i]&&C.c[i]<C.pdH[i]&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-1])return -1;
  return 0;
}],

// G6: Consecutive-bar exhaustion (5+ same-direction closes → fade)
// 5 consecutive higher closes = crowd is all in one direction = fade the extension
["G6: 5-bar consecutive fade", function(C,i){
  if(i<6||C.atr[i]==null||C.bbU[i]==null)return 0;
  let allUp=true,allDn=true;
  for(let k=1;k<=5;k++){if(C.c[i-k]<=C.c[i-k-1])allUp=false;if(C.c[i-k]>=C.c[i-k-1])allDn=false;}
  // Add BB stretch confirmation: price at/near band
  if(allUp&&C.c[i-1]>=C.bbU[i]&&C.c[i]<C.c[i-1])return -1;
  if(allDn&&C.c[i-1]<=C.bbL[i]&&C.c[i]>C.c[i-1])return  1;
  return 0;
}],

// G7: NR7 compression breakout failure
// Price makes an NR7 (narrowest range in 7 bars = volatility squeeze),
// then the NEXT bar breaks out of the NR7 range but REVERSES by close
// (false breakout of a compression = great fade opportunity)
["G7: NR7 false-breakout fade", function(C,i){
  if(i<2||C.atr[i]==null)return 0;
  if(!C.nr7[i-1])return 0; // prior bar must be NR7
  const nrH=C.h[i-1],nrL=C.l[i-1];
  // Current bar broke above NR7 high but closed back inside → short
  if(C.h[i]>nrH&&C.c[i]<=nrH&&C.c[i]<C.o[i])return -1;
  // Broke below NR7 low, closed back inside → long
  if(C.l[i]<nrL&&C.c[i]>=nrL&&C.c[i]>C.o[i])return  1;
  return 0;
}],

// G8: Morning-star / Evening-star 3-bar pattern
// Classic candlestick reversal: big down bar, tiny doji-ish bar, big up bar = morning star
["G8: Morning/evening star", function(C,i){
  if(i<2||C.atr[i]==null)return 0;
  const a=C.atr[i];
  // Bar i-2: big directional bar
  const bar2body=Math.abs(C.c[i-2]-C.o[i-2]);
  const bar1body=Math.abs(C.c[i-1]-C.o[i-1]);
  const bar0body=Math.abs(C.c[i]-C.o[i]);
  if(bar2body<0.5*a)return 0; // bar i-2 must be big
  if(bar1body>0.4*a)return 0; // bar i-1 must be small (the star)
  if(bar0body<0.4*a)return 0; // bar i must be big confirming
  // Morning star: big bear, doji, big bull
  if(C.c[i-2]<C.o[i-2]&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-2])return  1;
  // Evening star: big bull, doji, big bear
  if(C.c[i-2]>C.o[i-2]&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-2])return -1;
  return 0;
}],

// G9: Double-tap level fade (2 tests of same price level → fade 3rd approach)
// Price tests the same ±0.25ATR zone twice within the session, reject both times
// Third approach = high probability fade
["G9: Double-tap level fade", function(C,i){
  if(i<10||C.atr[i]==null||C.hod[i]==null)return 0;
  const a=C.atr[i],tol=0.25*a;
  // Look back 20 bars for 2 prior lows that are within tol of current bar's low
  let hiTouches=0,loTouches=0;
  for(let k=i-2;k>=Math.max(0,i-20);k--){
    if(Math.abs(C.l[k]-C.l[i])<tol)loTouches++;
    if(Math.abs(C.h[k]-C.h[i])<tol)hiTouches++;
  }
  const rng=C.h[i]-C.l[i];if(rng<0.001)return 0;
  const topThird=(C.c[i]-C.l[i])/rng>0.6;
  const botThird=(C.h[i]-C.c[i])/rng>0.6;
  // 2+ prior touches of this low + current bar bounces (closes in top third) → long
  if(loTouches>=2&&topThird&&C.c[i]>C.o[i])return  1;
  // 2+ prior touches of this high + current bar rejects (closes in bottom third) → short
  if(hiTouches>=2&&botThird&&C.c[i]<C.o[i])return -1;
  return 0;
}],

// G10: VWAP reclaim with trend
// Price was below VWAP, then a strong bar crosses back above VWAP AND
// EMA200 is above (so we're in an uptrend fading a pullback to VWAP)
// The reclaim is a momentum + mean-reversion hybrid
["G10: VWAP reclaim + trend", function(C,i){
  if(i<2)return 0;
  if(C.vwap[i]==null||C.ema200[i]==null||C.atr[i]==null)return 0;
  const vw=C.vwap[i];
  // Long: was below VWAP, now closes above, in uptrend
  const reclaimUp=C.c[i-1]<vw&&C.c[i]>vw&&C.c[i]>C.ema200[i];
  // Short: was above VWAP, now closes below, in downtrend
  const reclaimDn=C.c[i-1]>vw&&C.c[i]<vw&&C.c[i]<C.ema200[i];
  if(reclaimUp&&C.c[i]>C.o[i])return  1;
  if(reclaimDn&&C.c[i]<C.o[i])return -1;
  return 0;
}],

// G11 BONUS: Lunch-hour comeback (12:00-13:30 ET compression → 14:00 continuation)
// After a quiet lunch (tight range), the first breakout bar after 14:00 ET
// in the direction of the morning trend (above/below VWAP at noon)
["G11: Post-lunch trend continuation", function(C,i){
  if(C.vwap[i]==null||C.atr[i]==null)return 0;
  // Only fire 14:00-15:00 ET (mins 840-900)
  // We don't have ET.dm in C - need to compute on the fly... skip
  // Actually we built ET outside, but C doesn't hold it. Skip mins filter,
  // use the concept differently: after a NR4 bar, momentum breakout with VWAP bias
  if(!C.nr4[i-1])return 0; // prior bar was tight
  const rng4=C.h[i-1]-C.l[i-1];
  // Breakout bar: current bar range > 1.5x prior NR4 bar
  if((C.h[i]-C.l[i])<1.5*rng4)return 0;
  if(C.vwap[i]==null)return 0;
  // Trade in direction of VWAP bias + momentum
  if(C.c[i]>C.vwap[i]&&C.c[i]>C.h[i-1])return  1;
  if(C.c[i]<C.vwap[i]&&C.c[i]<C.l[i-1])return -1;
  return 0;
}],

];

const CONFIGS=[
  {stopMult:1.5,tgtMult:2.0,riskCap:200,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
  {stopMult:1.5,tgtMult:2.0,riskCap:200,maxTr:2,dayStop:-500,fee:FEE,slipTicks:SLIP},
  {stopMult:1.2,tgtMult:2.0,riskCap:200,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
  {stopMult:1.5,tgtMult:2.5,riskCap:200,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
  {stopMult:1.5,tgtMult:2.0,riskCap:200,maxTr:3,dayStop:-700,fee:FEE,slipTicks:SLIP},
  {stopMult:1.5,tgtMult:3.0,riskCap:200,maxTr:2,dayStop:-700,fee:FEE,slipTicks:SLIP},
];

const dol=x=>(x>=0?"+$":"-$")+Math.abs(Math.round(x)).toLocaleString();
const pct=x=>x.toFixed(1)+"%";
const Inf=Infinity;

(function main(){
  console.log("Loading...");
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
      const p=CONFIGS[ci],r13=run13(fn,p),rF=runFull(fn,p);
      if(r13.net$>best13){best13=r13.net$;const cp=cPass(rF.trades),m=mc(rF.trades);bestR={r13,rF,cp,m};bestCfg=p;}
    }
    console.log("13d "+dol(bestR.r13.net$)+"  full "+dol(bestR.rF.net$));
    results.push({name,cfg:bestCfg,r13:bestR.r13,rF:bestR.rF,cp:bestR.cp,mc:bestR.m});
  }

  results.sort((a,b)=>b.r13.net$-a.r13.net$);

  console.log("\n"+"=".repeat(130));
  console.log("  GEN-3 STRATEGY BATTLE - 13-DAY WINDOW");
  console.log("=".repeat(130));
  console.log("Strategy".padEnd(35)+" Config".padEnd(24)+"13d-Net".padStart(10)+"Trd/Win".padStart(11)+"PF".padStart(6)+" | "+"Full-Net".padStart(10)+"Win".padStart(8)+"DD".padStart(10)+"Feas".padStart(6)+"Comb".padStart(10)+"MC%".padStart(7));
  console.log("-".repeat(130));
  for(const r of results){
    const cfg="s"+r.cfg.stopMult+"/t"+r.cfg.tgtMult+" $"+r.cfg.riskCap+" "+r.cfg.maxTr+"/d";
    console.log(r.name.slice(0,34).padEnd(35)+cfg.padEnd(24)+
      dol(r.r13.net$).padStart(10)+(r.r13.n+"t "+pct(r.r13.win)).padStart(11)+String(r.r13.pf).padStart(6)+
      " | "+dol(r.rF.net$).padStart(10)+pct(r.rF.win).padStart(8)+("-$"+r.rF.maxDD$).padStart(10)+
      (r.rF.feasible?"YES":"NO ").padStart(6)+(r.cp.passed?"PASS":"FAIL-"+r.cp.why).padStart(10)+(r.mc+"%").padStart(7));
  }

  console.log("\n"+"=".repeat(130));
  console.log("  TOP 3 DAY-BY-DAY");
  for(let ti=0;ti<Math.min(3,results.length);ti++){
    const r=results[ti];
    console.log("\n["+(ti+1)+"] "+r.name);
    console.log("    Config: s"+r.cfg.stopMult+"/t"+r.cfg.tgtMult+" $"+r.cfg.riskCap+", "+r.cfg.maxTr+"/day, "+r.cfg.dayStop+" stop");
    console.log("    13d: "+dol(r.r13.net$)+" | "+r.r13.n+" trades | "+pct(r.r13.win)+" win | PF "+r.r13.pf+" | MaxDD -$"+r.r13.maxDD$);
    console.log("    Full: "+dol(r.rF.net$)+" | "+r.rF.n+" trades | "+pct(r.rF.win)+" win | MaxDD -$"+r.rF.maxDD$+" | Feasible: "+(r.rF.feasible?"YES":"NO"));
    console.log("    Combine: "+(r.cp.passed?"PASS":"FAIL("+r.cp.why+")")+" | MC: "+r.mc+"%");
    if(r.r13.byd&&r.r13.byd.size){
      const s=Array.from(r.r13.byd.entries()).sort((a,b)=>a[0].localeCompare(b[0]));
      for(const[day,pnl]of s)console.log("      "+day+": "+dol(pnl));
    }
  }

  // markdown
  const lines=["# Gen-3 Strategy Battle - 13d ("+new Date().toISOString().slice(0,10)+")","",
    "**10 brand-new entry edges.** Same risk model: $200 cap, vol-sized, max 5 MNQ, daily stop -$700, net of fee+2-tick slip.","",
    "| # | Strategy | Config | 13d Net | 13d Trd | 13d Win | 13d PF | Full Net | Full Win | DD | Feasible | Combine | MC% |",
    "|---|---|---|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|---:|"];
  for(let ri=0;ri<results.length;ri++){
    const r=results[ri];
    lines.push("| "+(ri+1)+" | "+r.name+" | s"+r.cfg.stopMult+"/t"+r.cfg.tgtMult+" $"+r.cfg.riskCap+" "+r.cfg.maxTr+"/d | "+
      dol(r.r13.net$)+" | "+r.r13.n+" | "+pct(r.r13.win)+" | "+r.r13.pf+" | "+dol(r.rF.net$)+" | "+pct(r.rF.win)+" | -$"+r.rF.maxDD$+" | "+(r.rF.feasible?"YES":"NO")+" | "+(r.cp.passed?"PASS":"FAIL-"+r.cp.why)+" | "+r.mc+"% |");
  }
  lines.push("","## Top 3 Day-by-Day","");
  for(let ti=0;ti<Math.min(3,results.length);ti++){
    const r=results[ti];
    lines.push("### "+(ti+1)+". "+r.name);
    lines.push("- 13d: "+dol(r.r13.net$)+" | "+r.r13.n+" trades | "+pct(r.r13.win)+" win | PF "+r.r13.pf+" | MaxDD -$"+r.r13.maxDD$);
    lines.push("- Full: "+dol(r.rF.net$)+" | "+r.rF.n+"t | "+pct(r.rF.win)+" win | MaxDD -$"+r.rF.maxDD$+" | Feasible: "+(r.rF.feasible?"YES":"NO"));
    lines.push("- Combine: "+(r.cp.passed?"PASS":"FAIL("+r.cp.why+")")+" | MC: "+r.mc+"%");
    if(r.r13.byd&&r.r13.byd.size){
      lines.push("");lines.push("| Date | P&L |");lines.push("|---|---|");
      const s=Array.from(r.r13.byd.entries()).sort((a,b)=>a[0].localeCompare(b[0]));
      for(const[day,pnl]of s)lines.push("| "+day+" | "+dol(pnl)+" |");
    }
    lines.push("");
  }
  fs.writeFileSync(path.join(__dirname,"logs","strat-gen3-13d-report.md"),lines.join("\n")+"\n");
  console.log("\nSaved: logs/strat-gen3-13d-report.md");
})();
