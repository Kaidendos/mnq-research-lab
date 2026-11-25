// strat-gen8-configs.js — 3 brand-new strategies + exhaustive config grid
// Champion to beat: K8 (I9 + $400 risk) — 9 days to pass, 88% MC, +$9,300 full
//
// NEW SIGNAL IDEAS (never tried):
//  L1: Engulfing bar at BB — 2-bar bullish/bearish engulfing right at Bollinger band
//      Simpler and more frequent than 3-bar morning star, same BB anchor
//  L2: VWAP reclaim + volume — price crosses VWAP with a strong high-volume bar
//      When institutions push price back above/below fair value with conviction
//  L3: 3-bar swing exhaustion — 3 consecutive bars each printing new extreme
//      (shorter window than 5-bar KeyRev), 4th bar reverses with body close
//      Tries to catch earlier in the reversal cycle
//
// CONFIG GRID per strategy: 
//  stopMult  × tgtMult × riskCap × maxTr  (no time filter vs 10am+ filter)
//  [1.0,1.2,1.5,1.8] × [1.5,2.0,2.5,3.0] × [200,300,400,500] × [2,3]
//  = 4×4×4×2 = 128 configs per signal × 2 (filtered/unfiltered) = 256 total per strategy
//  Best config selected by: 13d net (primary), feasibility gate required
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
  const atr=I.atr(h,l,c,14);
  const bb20=I.sma(c,20),bbS=I.stdev(c,20);
  const bbU=bb20.map((v2,i2)=>v2==null?null:v2+2*bbS[i2]);
  const bbL=bb20.map((v2,i2)=>v2==null?null:v2-2*bbS[i2]);
  const vol20=I.sma(v,20);
  const ema200=I.ema(c,200);
  const vwap=new Array(n).fill(null),vsd=new Array(n).fill(null);
  let vN=0,vD=0,vN2=0,curD=null;
  const hiVol=new Array(n).fill(false);
  for(let i=0;i<n;i++){
    const dk=ET.dk[i],inR=ET.rth[i];
    if(dk!==curD){vN=vD=vN2=0;curD=dk;}
    if(inR){
      const hlc3=(h[i]+l[i]+c[i])/3,vol=v[i]||1;
      vN+=hlc3*vol;vN2+=hlc3*hlc3*vol;vD+=vol;
      if(vD>0){const m=vN/vD;vwap[i]=m;vsd[i]=Math.sqrt(Math.max(0,vN2/vD-m*m));}
    }
    if(vol20[i]!=null)hiVol[i]=(v[i]||0)>1.4*vol20[i];
  }
  return{o,h,l,c,v,n,atr,bbU,bbL,bb20,vol20,ema200,vwap,vsd,hiVol,etMins:ET.dm,etRTH:ET.rth};
}

// ─── SIGNAL DEFINITIONS ────────────────────────────────────────────────────

// L1: Engulfing bar at BB band
// Current bar completely engulfs prior bar (open > prior high/low, close reverses past prior open)
// AND the engulfing bar touches or breaches the BB band
// Why it's different from morning star: only 2 bars, fires more often, no doji requirement
function sigL1(C,i){
  // Body engulf at BB: current body (open-close range) fully contains prior body
  // More lenient than wick engulf - fires more on 5-min bars
  if(i<1||C.bbU[i]==null||C.atr[i]==null)return 0;
  const prevH=Math.max(C.o[i-1],C.c[i-1]),prevL=Math.min(C.o[i-1],C.c[i-1]);
  const curH=Math.max(C.o[i],C.c[i]),curL=Math.min(C.o[i],C.c[i]);
  const priorBearish=C.c[i-1]<C.o[i-1],priorBullish=C.c[i-1]>C.o[i-1];
  // Bullish engulf: current bar green, body engulfs prior red bar body, at lower BB
  const bullEngulf=priorBearish&&C.c[i]>C.o[i]&&curL<=prevL&&curH>=prevH&&curH-curL>0.4*C.atr[i];
  // Bearish engulf: current bar red, body engulfs prior green bar body, at upper BB
  const bearEngulf=priorBullish&&C.c[i]<C.o[i]&&curL<=prevL&&curH>=prevH&&curH-curL>0.4*C.atr[i];
  if(bullEngulf&&C.l[i]<=C.bbL[i]+0.3*C.atr[i]&&C.c[i]>C.bbL[i])return 1;
  if(bearEngulf&&C.h[i]>=C.bbU[i]-0.3*C.atr[i]&&C.c[i]<C.bbU[i])return -1;
  return 0;
}

// L2: VWAP reclaim with volume conviction
// Price was below VWAP for 2+ bars, then a high-volume bar closes above VWAP
// (or above → below for shorts)
// The volume spike = institutions stepping in at fair value
function sigL2(C,i){
  if(i<3||C.vwap[i]==null||C.atr[i]==null||!C.hiVol[i])return 0;
  const vw=C.vwap[i];
  // Was below VWAP for at least 2 prior bars
  const wasBelow=C.c[i-1]<vw&&C.c[i-2]<vw;
  // Was above VWAP for at least 2 prior bars
  const wasAbove=C.c[i-1]>vw&&C.c[i-2]>vw;
  // Current bar reclaims: strong bullish close above VWAP
  const reclaimUp=wasBelow&&C.c[i]>vw&&C.c[i]>C.o[i]&&(C.c[i]-C.o[i])>0.3*C.atr[i];
  // Current bar loses: strong bearish close below VWAP
  const reclaimDn=wasAbove&&C.c[i]<vw&&C.c[i]<C.o[i]&&(C.o[i]-C.c[i])>0.3*C.atr[i];
  if(reclaimUp)return 1;
  if(reclaimDn)return -1;
  return 0;
}

// L3: 3-bar swing exhaustion reversal
// 3 consecutive bars EACH making a new low (or high) beyond the prior bar
// Then the current bar (bar 4) reverses: closes opposite with body in reversal direction
// Shorter window than 5-bar KeyRev → catches turns earlier in the move
function sigL3(C,i){
  if(i<3||C.atr[i]==null)return 0;
  // 3-bar lower lows
  const newLow3=C.l[i-1]<C.l[i-2]&&C.l[i-2]<C.l[i-3];
  // 3-bar higher highs
  const newHigh3=C.h[i-1]>C.h[i-2]&&C.h[i-2]>C.h[i-3];
  // Bar 4 reversal: needs meaningful body in reversal direction
  const bullBody=C.c[i]>C.o[i]&&(C.c[i]-C.o[i])>0.3*C.atr[i]&&C.c[i]>C.c[i-1];
  const bearBody=C.c[i]<C.o[i]&&(C.o[i]-C.c[i])>0.3*C.atr[i]&&C.c[i]<C.c[i-1];
  if(newLow3&&bullBody)return 1;
  if(newHigh3&&bearBody)return -1;
  return 0;
}

// Time-filtered versions (10am-3:30pm ET only, same as J10 which proved better)
function sigL1f(C,i){if(!C.etMins||C.etMins[i]<600||C.etMins[i]>=930)return 0;return sigL1(C,i);}
function sigL2f(C,i){if(!C.etMins||C.etMins[i]<600||C.etMins[i]>=930)return 0;return sigL2(C,i);}
function sigL3f(C,i){if(!C.etMins||C.etMins[i]<600||C.etMins[i]>=930)return 0;return sigL3(C,i);}

// ─── SIMULATION ────────────────────────────────────────────────────────────

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
        trades.push({pnl,day:dk});pos=null;i++;continue;
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
  let cum=0,pk=0;const bd=new Map(),days=new Set();
  for(const t of trades){
    days.add(t.day);cum+=t.pnl;pk=Math.max(pk,cum);
    bd.set(t.day,(bd.get(t.day)||0)+t.pnl);
    if(pk-cum>=MLL)return{passed:false,why:"MLL",days:days.size};
    if(bd.get(t.day)<=-DLL)return{passed:false,why:"DLL",days:days.size};
    if(cum>=TARGET)return{passed:true,why:"target",days:days.size};
  }return{passed:false,why:"no-target",days:days.size};
}
function mc(trades,iters){
  iters=iters||2000;if(!trades.length)return{pct:0,medDays:null,under13:0};
  const p=trades.map(t=>t.pnl),d=trades.map(t=>t.day);
  let pass=0,under13=0;const passDays=[];
  for(let it=0;it<iters;it++){
    const idx=Array.from({length:p.length},(_,k)=>k);
    for(let k=idx.length-1;k>0;k--){const j=(Math.random()*(k+1))|0;const t=idx[k];idx[k]=idx[j];idx[j]=t;}
    let cum=0,pk=0,ok=false,dead=false;const ds=new Set();
    for(let k=0;k<idx.length;k++){
      const ii=idx[k];ds.add(d[ii]);cum+=p[ii];pk=Math.max(pk,cum);
      if(pk-cum>=MLL){dead=true;break;}
      if(cum>=TARGET){ok=true;break;}
    }
    if(ok&&!dead){pass++;passDays.push(ds.size);if(ds.size<=13)under13++;}
  }
  passDays.sort((a,b)=>a-b);
  return{pct:+(pass/iters*100).toFixed(1),
    medDays:passDays.length?passDays[Math.floor(passDays.length/2)]:null,
    under13:pass>0?+(under13/pass*100).toFixed(0):0};
}

// ─── CONFIG GRID ───────────────────────────────────────────────────────────

const STOP_MULTS=[1.0,1.2,1.5,1.8];
const TGT_MULTS=[1.5,2.0,2.5,3.0];
const RISK_CAPS=[200,300,400,500];
const MAX_TRS=[2,3];
// 4×4×4×2 = 128 configs × 2 (filtered/unfiltered) = 256 per strategy

function gridSearch(allBars,C,ET,sigRaw,sigFilt,cutT,label){
  function run13(fn,p){return sim(allBars,C,ET,(C2,i)=>allBars[i].t>=cutT?fn(C2,i):0,p);}
  function runFull(fn,p){return sim(allBars,C,ET,fn,p);}

  let best=null,bestScore=-Infinity;
  let tested=0;
  for(const filtered of[false,true]){
    const fn=filtered?sigFilt:sigRaw;
    for(const stopMult of STOP_MULTS){
      for(const tgtMult of TGT_MULTS){
        for(const riskCap of RISK_CAPS){
          for(const maxTr of MAX_TRS){
            const p={stopMult,tgtMult,riskCap,maxTr,dayStop:-700,fee:FEE,slipTicks:SLIP};
            const r13=run13(fn,p),rF=runFull(fn,p);
            if(!rF.feasible||rF.net$<=0){tested++;continue;}
            // Score: weight 13d net heavily (that's the eval window)
            // but penalize if full-period is weak
            const score=r13.net$*2+rF.net$;
            if(score>bestScore){
              bestScore=score;
              const cp=cPass(rF.trades),m=mc(rF.trades);
              best={r13,rF,cp,m,p,filtered};
            }
            tested++;
          }
        }
      }
    }
  }
  process.stdout.write(" ["+tested+" configs tested]\n");
  return best;
}

const dol=x=>(x>=0?"+$":"-$")+Math.abs(Math.round(x)).toLocaleString();
const pct=x=>x.toFixed(1)+"%";

(function main(){
  console.log("Gen-8: 3 new strategies + config grid (256 configs each)...");
  const allBars=JSON.parse(fs.readFileSync(path.join(__dirname,"data","nq-5m.json"),"utf8"))
    .filter(b=>b&&isFinite(b.c)).sort((a,b)=>a.t-b.t);
  const ET=preET(allBars);
  const daySet=new Set();
  for(let i=0;i<allBars.length;i++)if(ET.rth[i])daySet.add(ET.dk[i]);
  const rthDays=Array.from(daySet).sort();
  const last13=rthDays.slice(-13);
  const cutT=(()=>{for(let i=0;i<allBars.length;i++)if(ET.dk[i]===last13[0])return allBars[i].t;return Infinity;})();
  console.log("13d: "+last13[0]+" to "+last13[last13.length-1]+" | "+rthDays.length+" RTH days total");
  const C=buildCtx(allBars,ET);

  const STRATS=[
    {label:"L1: Engulfing@BB",raw:sigL1,filt:sigL1f},
    {label:"L2: VWAP reclaim+vol",raw:sigL2,filt:sigL2f},
    {label:"L3: 3-bar exhaustion",raw:sigL3,filt:sigL3f},
  ];

  const results=[];
  for(const s of STRATS){
    process.stdout.write("  Searching "+s.label+"...");
    const best=gridSearch(allBars,C,ET,s.raw,s.filt,cutT,s.label);
    if(!best){console.log("  NO FEASIBLE CONFIG FOUND for "+s.label);continue;}
    results.push({name:s.label,...best});
  }

  console.log("\n"+"=".repeat(160));
  console.log("  GEN-8 BEST CONFIGS — sorted by days-to-pass (fewest first)");
  console.log("=".repeat(160));
  console.log("Strategy".padEnd(26)+"Config".padEnd(36)+"Filter".padEnd(8)+"13d".padStart(9)+"T".padStart(5)+"Win".padStart(7)+"PF".padStart(5)+" | Full".padStart(8)+"DD".padStart(9)+"F".padStart(3)+" Combine".padStart(9)+"Days".padStart(6)+"MC%".padStart(7)+"Med".padStart(6)+"U13".padStart(6));
  console.log("-".repeat(160));

  results.sort((a,b)=>{
    if(a.cp.passed&&!b.cp.passed)return -1;
    if(!a.cp.passed&&b.cp.passed)return 1;
    if(a.cp.passed&&b.cp.passed)return a.cp.days-b.cp.days;
    return b.m.under13-a.m.under13;
  });

  for(const r of results){
    const p=r.p;
    const cfg="s"+p.stopMult+"/t"+p.tgtMult+" $"+p.riskCap+" "+p.maxTr+"/d";
    const star=r.rF.feasible&&r.rF.net$>0?"*":" ";
    console.log((star+r.name).slice(0,25).padEnd(26)+cfg.padEnd(36)+(r.filtered?"10am+":"all ").padEnd(8)+
      dol(r.r13.net$).padStart(9)+String(r.r13.n).padStart(5)+pct(r.r13.win).padStart(7)+String(r.r13.pf).padStart(5)+
      " | "+dol(r.rF.net$).padStart(6)+("-$"+r.rF.maxDD$).padStart(9)+(r.rF.feasible?"Y":"N").padStart(3)+
      (r.cp.passed?"PASS":"FAIL-"+r.cp.why).padStart(9)+(r.cp.passed?String(r.cp.days):"--").padStart(6)+
      String(r.m.pct+"%").padStart(7)+String(r.m.medDays||"--").padStart(6)+String(r.m.under13+"%").padStart(6));
  }

  // Detailed breakdown for each
  console.log("\n--- DETAILED RESULTS ---");
  for(let ti=0;ti<results.length;ti++){
    const r=results[ti];
    const p=r.p;
    console.log("\n["+(ti+1)+"] "+r.name+" | s"+p.stopMult+"/t"+p.tgtMult+" $"+p.riskCap+" "+p.maxTr+"/d | "+(r.filtered?"10am+ filter":"all session"));
    console.log("    13d: "+dol(r.r13.net$)+" | "+r.r13.n+"t | "+pct(r.r13.win)+" win | PF "+r.r13.pf+" | DD -$"+r.r13.maxDD$);
    console.log("    Full: "+dol(r.rF.net$)+" | "+r.rF.n+"t | "+pct(r.rF.win)+" | DD -$"+r.rF.maxDD$+" | "+(r.rF.feasible?"FEASIBLE":"BUST"));
    console.log("    Combine: "+(r.cp.passed?"PASS in "+r.cp.days+" trading days":"FAIL("+r.cp.why+")")+" | MC: "+r.m.pct+"% | Median: "+r.m.medDays+"d | Under-13: "+r.m.under13+"%");
    if(r.r13.byd&&r.r13.byd.size){
      const s=Array.from(r.r13.byd.entries()).sort((a,b)=>a[0].localeCompare(b[0]));
      let cum=0;
      for(const[day,pnl]of s){cum+=pnl;console.log("      "+day+": "+dol(pnl)+" (cum: "+dol(cum)+")");}
    }
  }

  // Compare to K8 champion
  console.log("\n=== vs K8 CHAMPION (I9 + $400, 2/d) ===");
  console.log("K8: 13d +$1,654 | Full +$9,300 | DD -$1,887 | PASS in 9 days | MC 88.1% | Under-13: 19%");
  for(const r of results){
    if(r.cp.passed){
      const faster=r.cp.days<9?"FASTER than K8 by "+(9-r.cp.days)+"d":"slower by "+(r.cp.days-9)+"d";
      const richer=r.rF.net$>9300?"richer by $"+(r.rF.net$-9300):"poorer by $"+(9300-r.rF.net$);
      console.log(r.name+": Pass in "+r.cp.days+"d ("+faster+"), "+richer);
    }else{
      console.log(r.name+": No Combine pass — MC "+r.m.pct+"%");
    }
  }

  // Save report
  const lines=["# Gen-8: New Strategies + Config Grid ("+new Date().toISOString().slice(0,10)+")",
    "","**Reference to beat: K8 — I9 portfolio + $400 risk → PASS in 9 days, 88% MC, +$9,300 full**","",
    "## Config grid: 4 stop × 4 target × 4 riskCap × 2 maxTr × 2 (all/filtered) = 256 configs tested per strategy","",
    "| # | Strategy | Best Config | Filter | 13d | Trades | Win | PF | Full | DD | F | Combine | Days | MC% | MedD | U13% |",
    "|---|---|---|---|---:|---:|---:|---:|---:|---:|:--:|:---:|---:|---:|---:|---:|"];
  for(let ri=0;ri<results.length;ri++){
    const r=results[ri],p=r.p;
    lines.push("| "+(ri+1)+" | "+r.name+" | s"+p.stopMult+"/t"+p.tgtMult+" $"+p.riskCap+" "+p.maxTr+"/d | "+
      (r.filtered?"10am+":"all")+" | "+dol(r.r13.net$)+" | "+r.r13.n+" | "+pct(r.r13.win)+" | "+r.r13.pf+" | "+
      dol(r.rF.net$)+" | -$"+r.rF.maxDD$+" | "+(r.rF.feasible?"Y":"N")+" | "+
      (r.cp.passed?"PASS":"FAIL-"+r.cp.why)+" | "+(r.cp.passed?r.cp.days:"--")+" | "+
      r.m.pct+"% | "+(r.m.medDays||"--")+" | "+r.m.under13+"% |");
  }
  lines.push("","## Day-by-day (13d window)","");
  for(const r of results){
    const p=r.p;
    lines.push("### "+r.name+" — s"+p.stopMult+"/t"+p.tgtMult+" $"+p.riskCap+" "+p.maxTr+"/d "+(r.filtered?"(10am+)":"(all session)"));
    if(r.r13.byd&&r.r13.byd.size){
      lines.push("| Date | P&L | Running |","|---|---|---|");
      const s=Array.from(r.r13.byd.entries()).sort((a,b)=>a[0].localeCompare(b[0]));
      let cum=0;for(const[d,pval]of s){cum+=pval;lines.push("| "+d+" | "+dol(pval)+" | "+dol(cum)+" |");}
    }
    lines.push("");
  }
  fs.writeFileSync(path.join(__dirname,"logs","strat-gen8-configs-report.md"),lines.join("\n")+"\n");
  console.log("\nSaved: logs/strat-gen8-configs-report.md");
})();
