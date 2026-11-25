// strat-gen9-combo.js — L1 + K8 portfolio combination + config grid
// Current champions:
//   L1: Engulfing@BB — 6 days to pass, 85% MC, 64% under-13, +$12,307 full
//   K8: I9 (morning star + KeyRev@BB+vol, $400) — 9 days, 88% MC, 19% under-13
// Theory: L1 fires ~5t/13d, I9 fires ~26t/13d. Different pattern types covering different bars.
// Combined portfolio = more signals, same quality gates. Target: pass faster and more consistently.
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
  const vwap=new Array(n).fill(null);
  let vN=0,vD=0,curD=null;
  const hiVol=new Array(n).fill(false);
  for(let i=0;i<n;i++){
    const dk=ET.dk[i],inR=ET.rth[i];
    if(dk!==curD){vN=vD=0;curD=dk;}
    if(inR){const hlc3=(h[i]+l[i]+c[i])/3,vol=v[i]||1;vN+=hlc3*vol;vD+=vol;if(vD>0)vwap[i]=vN/vD;}
    if(vol20[i]!=null)hiVol[i]=(v[i]||0)>1.4*vol20[i];
  }
  return{o,h,l,c,v,n,atr,bbU,bbL,vol20,ema200,vwap,hiVol,etMins:ET.dm,etRTH:ET.rth};
}

// ─── SIGNALS ───────────────────────────────────────────────────────────────

function sigL1(C,i){
  if(i<1||C.bbU[i]==null||C.atr[i]==null)return 0;
  const prevH=Math.max(C.o[i-1],C.c[i-1]),prevL=Math.min(C.o[i-1],C.c[i-1]);
  const curH=Math.max(C.o[i],C.c[i]),curL=Math.min(C.o[i],C.c[i]);
  const priorBearish=C.c[i-1]<C.o[i-1],priorBullish=C.c[i-1]>C.o[i-1];
  const bullEngulf=priorBearish&&C.c[i]>C.o[i]&&curL<=prevL&&curH>=prevH&&curH-curL>0.4*C.atr[i];
  const bearEngulf=priorBullish&&C.c[i]<C.o[i]&&curL<=prevL&&curH>=prevH&&curH-curL>0.4*C.atr[i];
  if(bullEngulf&&C.l[i]<=C.bbL[i]+0.3*C.atr[i]&&C.c[i]>C.bbL[i])return 1;
  if(bearEngulf&&C.h[i]>=C.bbU[i]-0.3*C.atr[i]&&C.c[i]<C.bbU[i])return -1;
  return 0;
}
function sigI9(C,i){
  if(i<5||C.atr[i]==null)return 0;
  // Morning star
  if(i>=2){
    const a=C.atr[i];
    const b2=Math.abs(C.c[i-2]-C.o[i-2]),b1=Math.abs(C.c[i-1]-C.o[i-1]),b0=Math.abs(C.c[i]-C.o[i]);
    if(b2>=0.5*a&&b1<=0.4*a&&b0>=0.4*a){
      if(C.c[i-2]<C.o[i-2]&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-2])return 1;
      if(C.c[i-2]>C.o[i-2]&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-2])return -1;
    }
  }
  // KeyRev@BB + high volume
  if(C.bbU[i]==null||!C.hiVol[i])return 0;
  let nl=true,nh=true;
  for(let q=1;q<=5;q++){if(C.l[i]>=C.l[i-q])nl=false;if(C.h[i]<=C.h[i-q])nh=false;}
  if(nl&&C.c[i]>C.o[i]&&C.c[i]>C.c[i-1]&&C.l[i]<=C.bbL[i]&&C.c[i]>C.bbL[i])return 1;
  if(nh&&C.c[i]<C.o[i]&&C.c[i]<C.c[i-1]&&C.h[i]>=C.bbU[i]&&C.c[i]<C.bbU[i])return -1;
  return 0;
}

// Combo variants to test
const SIGNALS={
  "L1 only":       (C,i)=>sigL1(C,i),
  "I9 only":       (C,i)=>sigI9(C,i),
  "L1+I9":         (C,i)=>sigL1(C,i)||sigI9(C,i)||0,
  "L1+I9 (L1 pri)":(C,i)=>{const d=sigL1(C,i);return d||sigI9(C,i)||0;},
};
// Each tested with all-session and 10am+ filter
function filtered(fn){return(C,i)=>{if(!C.etMins||C.etMins[i]<600||C.etMins[i]>=930)return 0;return fn(C,i);};}

// ─── SIM + STATS ───────────────────────────────────────────────────────────

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

const STOP_MULTS=[1.0,1.2,1.5,1.8];
const TGT_MULTS=[1.5,2.0,2.5,3.0];
const RISK_CAPS=[200,300,400,500];
const MAX_TRS=[2,3];
const dol=x=>(x>=0?"+$":"-$")+Math.abs(Math.round(x)).toLocaleString();
const pct=x=>x.toFixed(1)+"%";

(function main(){
  console.log("Gen-9: L1 + I9 combo + config grid...");
  const allBars=JSON.parse(fs.readFileSync(path.join(__dirname,"data","nq-5m.json"),"utf8"))
    .filter(b=>b&&isFinite(b.c)).sort((a,b)=>a.t-b.t);
  const ET=preET(allBars);
  const daySet=new Set();
  for(let i=0;i<allBars.length;i++)if(ET.rth[i])daySet.add(ET.dk[i]);
  const rthDays=Array.from(daySet).sort();
  const last13=rthDays.slice(-13);
  const cutT=(()=>{for(let i=0;i<allBars.length;i++)if(ET.dk[i]===last13[0])return allBars[i].t;return Infinity;})();
  const C=buildCtx(allBars,ET);
  function run13(fn,p){return sim(allBars,C,ET,(C2,i2)=>allBars[i2].t>=cutT?fn(C2,i2):0,p);}
  function runFull(fn,p){return sim(allBars,C,ET,fn,p);}

  const allVariants=[];
  for(const[sname,sfn] of Object.entries(SIGNALS)){
    for(const useFilter of[false,true]){
      allVariants.push({name:sname+(useFilter?" 10am+":""),fn:useFilter?filtered(sfn):sfn});
    }
  }

  const results=[];
  for(const v of allVariants){
    process.stdout.write("  "+v.name+"... ");
    let best=null,bestScore=-Infinity;
    for(const stopMult of STOP_MULTS){
      for(const tgtMult of TGT_MULTS){
        for(const riskCap of RISK_CAPS){
          for(const maxTr of MAX_TRS){
            const p={stopMult,tgtMult,riskCap,maxTr,dayStop:-700,fee:FEE,slipTicks:SLIP};
            const r13=run13(v.fn,p),rF=runFull(v.fn,p);
            if(!rF.feasible||rF.net$<=0)continue;
            // Score: prioritize speed (Combine days), then 13d net
            const cp=cPass(rF.trades);
            const daysBonus=cp.passed?Math.max(0,60-cp.days)*200:0;
            const score=r13.net$*2+rF.net$+daysBonus;
            if(score>bestScore){
              bestScore=score;
              const m=mc(rF.trades);
              best={r13,rF,cp,m,p};
            }
          }
        }
      }
    }
    if(!best){console.log("no feasible config");continue;}
    console.log("13d "+dol(best.r13.net$)+" | full "+dol(best.rF.net$)+" | "+(best.cp.passed?"PASS "+best.cp.days+"d":"FAIL")+" | MC "+best.m.pct+"% U13="+best.m.under13+"%");
    results.push({name:v.name,...best});
  }

  // Sort: passed first, then fewest days, then highest under-13
  results.sort((a,b)=>{
    if(a.cp.passed&&!b.cp.passed)return -1;
    if(!a.cp.passed&&b.cp.passed)return 1;
    if(a.cp.passed&&b.cp.passed){
      if(a.cp.days!==b.cp.days)return a.cp.days-b.cp.days;
      return b.m.under13-a.m.under13;
    }
    return b.m.under13-a.m.under13;
  });

  console.log("\n"+"=".repeat(155));
  console.log("  GEN-9 COMBO RESULTS — fastest Combine pass wins");
  console.log("=".repeat(155));
  console.log("Variant".padEnd(28)+"Config".padEnd(28)+"13d".padStart(9)+"T".padStart(5)+"Win".padStart(7)+"PF".padStart(5)+" | Full".padStart(9)+"DD".padStart(9)+"F".padStart(3)+" Cmb".padStart(6)+"Days".padStart(6)+"MC%".padStart(7)+"Med".padStart(6)+"U13%".padStart(7));
  console.log("-".repeat(155));
  for(const r of results){
    const p=r.p;
    const cfg="s"+p.stopMult+"/t"+p.tgtMult+" $"+p.riskCap+" "+p.maxTr+"/d";
    const star=r.cp.passed?"*":" ";
    console.log((star+r.name).slice(0,27).padEnd(28)+cfg.padEnd(28)+
      dol(r.r13.net$).padStart(9)+String(r.r13.n).padStart(5)+pct(r.r13.win).padStart(7)+String(r.r13.pf).padStart(5)+
      " | "+dol(r.rF.net$).padStart(7)+("-$"+r.rF.maxDD$).padStart(9)+(r.rF.feasible?"Y":"N").padStart(3)+
      (r.cp.passed?"PASS":"FAIL").padStart(6)+(r.cp.passed?String(r.cp.days):"--").padStart(6)+
      String(r.m.pct+"%").padStart(7)+String(r.m.medDays||"--").padStart(6)+String(r.m.under13+"%").padStart(7));
  }

  const best=results[0];
  console.log("\n=== WINNER: "+best.name+" ===");
  console.log("Config: s"+best.p.stopMult+"/t"+best.p.tgtMult+" $"+best.p.riskCap+" "+best.p.maxTr+"/d");
  console.log("13d: "+dol(best.r13.net$)+" | "+best.r13.n+"t | "+pct(best.r13.win)+" win | PF "+best.r13.pf);
  console.log("Full: "+dol(best.rF.net$)+" | DD -$"+best.rF.maxDD$);
  console.log("Combine: "+(best.cp.passed?"PASS in "+best.cp.days+" trading days":"FAIL("+best.cp.why+")")+" | MC: "+best.m.pct+"% | Med: "+best.m.medDays+"d | U13: "+best.m.under13+"%");
  if(best.r13.byd&&best.r13.byd.size){
    const s=Array.from(best.r13.byd.entries()).sort((a,b2)=>a[0].localeCompare(b2[0]));
    let cum=0;for(const[d,pv]of s){cum+=pv;console.log("  "+d+": "+dol(pv)+" (running: "+dol(cum)+")");}
  }

  // Reference comparison
  console.log("\n=== vs PREVIOUS CHAMPIONS ===");
  console.log("L1 alone:  6d pass | 85% MC | 64% U13 | +$12,307 full");
  console.log("K8 I9+400: 9d pass | 88% MC | 19% U13 | +$9,300 full");
  if(best.cp.passed)
    console.log("COMBO:    "+best.cp.days+"d pass | "+best.m.pct+"% MC | "+best.m.under13+"% U13 | "+dol(best.rF.net$)+" full");

  // Save report
  const lines=["# Gen-9: L1+K8 Combo ("+new Date().toISOString().slice(0,10)+")",
    "","**Goal:** combine Engulfing@BB (L1) + I9 portfolio (morning star + KeyRev@BB+vol)","",
    "**Previous champions:** L1=6d/85%MC/64%U13 | K8=9d/88%MC/19%U13","",
    "| Variant | Config | 13d | T | Win | PF | Full | DD | F | Pass | Days | MC% | Med | U13% |",
    "|---|---|---:|---:|---:|---:|---:|---:|:--:|:---:|---:|---:|---:|---:|"];
  for(const r of results){
    const p=r.p,star=r.cp.passed?"* ":"";
    lines.push("| "+star+r.name+" | s"+p.stopMult+"/t"+p.tgtMult+" $"+p.riskCap+" "+p.maxTr+"/d | "+
      dol(r.r13.net$)+" | "+r.r13.n+" | "+pct(r.r13.win)+" | "+r.r13.pf+" | "+
      dol(r.rF.net$)+" | -$"+r.rF.maxDD$+" | "+(r.rF.feasible?"Y":"N")+" | "+
      (r.cp.passed?"PASS":"FAIL-"+r.cp.why)+" | "+(r.cp.passed?r.cp.days:"--")+" | "+
      r.m.pct+"% | "+(r.m.medDays||"--")+" | "+r.m.under13+"% |");
  }
  lines.push("","## Winner Day-by-Day","","**"+best.name+"** — s"+best.p.stopMult+"/t"+best.p.tgtMult+" $"+best.p.riskCap+" "+best.p.maxTr+"/d","");
  lines.push("| Date | P&L | Running |","|---|---|---|");
  if(best.r13.byd&&best.r13.byd.size){
    const s=Array.from(best.r13.byd.entries()).sort((a,b)=>a[0].localeCompare(b[0]));
    let cum=0;for(const[d,pv]of s){cum+=pv;lines.push("| "+d+" | "+dol(pv)+" | "+dol(cum)+" |");}
  }
  fs.writeFileSync(path.join(__dirname,"logs","strat-gen9-combo-report.md"),lines.join("\n")+"\n");
  console.log("\nSaved: logs/strat-gen9-combo-report.md");
  // Return winner config for best-strategy.js
  return{winner:best,name:best.name};
})();
