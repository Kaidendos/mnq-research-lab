// =============================================================
//  live-engulfing.js  —  AUTO-TRADE engine for the BEST strategy:
//  "Engulfing Bar at Bollinger Band (10am+ filter)"
//
//  MODES:
//   DRY-RUN (default): logs signals, posts Discord, no orders.
//   ARMED (ARMED=1):   places sim bracket orders on PRACTICE account XXXX.
//
//  STRATEGY: Engulfing body@BB(20,2) | 10am-3:30pm ET
//  Stop 1xATR | Target 3xATR | $400 risk cap | max 3/day | -$700 day stop
//
//  Run:
//    node live-engulfing.js              DRY-RUN loop
//    ARMED=1 node live-engulfing.js      LIVE auto-trade loop
//    node live-engulfing.js --once       evaluate once, exit
//    node live-engulfing.js --test       Discord test ping, exit
// =============================================================
"use strict";
const fs    = require("fs");
const path  = require("path");
require("./public/indicators.js");
const PX     = require("./projectx.js");
const Orders = require("./projectx-orders.js");
const Notify = require("./notify.js");

// Strategy params
const PV=2,MAXC=5,RISK_CAP=400,STOP_MULT=1.0,TGT_MULT=3.0;
const SCALE_ENABLED=false; // false = FIXED exit (1×ATR stop / 3×ATR target). true = partial scale-out.
const SCALE_FRAC=0.4,SCALE_R=1.5,MOVE_BE=true; // scale-out params (only used when SCALE_ENABLED)
const MAX_TR=3,DAY_STOP=-700,TICK=0.25,SLIP=2*TICK,FEE=0.37;
// Times match the best-strategy.js backtest exactly: entries 10:00am–3:30pm (600..930),
// open positions managed until RTH close 4:00pm (960), then force-flattened.
const RTH_S=570,RTH_E=960,TIME_FILT=600,ENTRY_CUT=930,MAX_BAR_AGE=900,POLL_MS=30000;
const ACCOUNT_ID=parseInt(process.env.PROJECTX_ACCOUNT_ID||"XXXX",10);
const TRADE_SYM=process.env.PROJECTX_TRADE_SYMBOL||"MNQ";
const STATE_FILE=process.env.ENGULF_STATE_FILE||path.join(__dirname,".engulf-state.json");
const DISARM_FILE=path.join(__dirname,".disarm");
const LOG_FILE=path.join(__dirname,"logs","live-engulfing.jsonl");
const LOCK_FILE=path.join(__dirname,".engulf-lock");
const HEARTBEAT_FILE=process.env.ENGULF_HEARTBEAT_FILE||path.join(__dirname,".engulf-heartbeat");
const HB_STALE_MS=3*60*1000;
function isDisarmed(){try{return fs.existsSync(DISARM_FILE);}catch{return false;}}
const ARMED=(process.env.ARMED||"").trim()==="1"&&!isDisarmed();

// ET helper
function toET(s){
  const u=s*1000,d=new Date(u),y=d.getUTCFullYear();
  const ms=new Date(Date.UTC(y,2,1));ms.setUTCDate(1+((7-ms.getUTCDay())%7)+7);
  const ns=new Date(Date.UTC(y,10,1));ns.setUTCDate(1+((7-ns.getUTCDay())%7));
  const off=(u>=ms.getTime()&&u<ns.getTime())?-240:-300;
  const et=new Date(u+off*60000);
  return{mins:et.getUTCHours()*60+et.getUTCMinutes(),
    dk:et.getUTCFullYear()+"-"+String(et.getUTCMonth()+1).padStart(2,"0")+"-"+String(et.getUTCDate()).padStart(2,"0"),
    hhmm:String(et.getUTCHours()).padStart(2,"0")+":"+String(et.getUTCMinutes()).padStart(2,"0"),
    dow:et.getUTCDay()};
}

// Signal: engulfing body at BB
function detectSignal(bars){
  if(bars.length<22)return null;
  const c=bars.map(b=>b.c),o=bars.map(b=>b.o),h=bars.map(b=>b.h),l=bars.map(b=>b.l);
  const I=globalThis.Indicators;
  const sma=I.sma(c,20),std=I.stdev(c,20),atr=I.atr(h,l,c,14);
  const bbU=sma.map((v,i)=>v==null?null:v+2*std[i]);
  const bbL=sma.map((v,i)=>v==null?null:v-2*std[i]);
  const i=bars.length-1;
  if(bbU[i]==null||atr[i]==null)return null;
  const pH=Math.max(o[i-1],c[i-1]),pL=Math.min(o[i-1],c[i-1]);
  const cH=Math.max(o[i],c[i]),cL=Math.min(o[i],c[i]);
  if(cH-cL<0.4*atr[i])return null;
  const engulfs=cL<=pL&&cH>=pH;
  if(c[i-1]<o[i-1]&&c[i]>o[i]&&engulfs&&l[i]<=bbL[i]+0.3*atr[i]&&c[i]>bbL[i])
    return{dir:1,close:c[i],atr:atr[i],barT:bars[i].t};
  if(c[i-1]>o[i-1]&&c[i]<o[i]&&engulfs&&h[i]>=bbU[i]-0.3*atr[i]&&c[i]<bbU[i])
    return{dir:-1,close:c[i],atr:atr[i],barT:bars[i].t};
  return null;
}

function loadState(){try{return JSON.parse(fs.readFileSync(STATE_FILE,"utf8"));}catch{return {};}}
function saveState(s){try{fs.writeFileSync(STATE_FILE,JSON.stringify(s,null,2));}catch{}}
function audit(e){try{fs.appendFileSync(LOG_FILE,JSON.stringify({...e,ts:new Date().toISOString()})+"\n");}catch{}}

// ── single-instance lock + heartbeat (only ever ONE armed bot may run) ──
function isAlive(pid){try{process.kill(pid,0);return true;}catch(e){return e.code==="EPERM";}}
function anotherInstanceRunning(){
  try{
    if(!fs.existsSync(LOCK_FILE))return false;
    const pid=parseInt(fs.readFileSync(LOCK_FILE,"utf8").trim(),10);
    if(!pid||pid===process.pid)return false;
    if(!isAlive(pid))return false;                       // lock-holder is dead → stale
    try{const hb=JSON.parse(fs.readFileSync(HEARTBEAT_FILE,"utf8"));
      if(hb.pid===pid&&(Date.now()-new Date(hb.ts).getTime())<HB_STALE_MS)return true;}catch{}
    return false;                                         // pid alive but heartbeat stale → take over
  }catch{return false;}
}
function writeLock(){try{fs.writeFileSync(LOCK_FILE,String(process.pid));}catch{}}
function releaseLock(){try{if(fs.existsSync(LOCK_FILE)&&parseInt(fs.readFileSync(LOCK_FILE,"utf8").trim(),10)===process.pid)fs.unlinkSync(LOCK_FILE);}catch{}}
function writeHeartbeat(extra){try{fs.writeFileSync(HEARTBEAT_FILE,JSON.stringify({ts:new Date().toISOString(),pid:process.pid,armed:ARMED,...extra}));}catch{}}
const f=x=>Number(x).toFixed(2);
const dol=x=>(x>=0?"+$":"-$")+Math.abs(Math.round(x)).toLocaleString();
const GREEN=0x00cc66,RED=0xff4444,BLUE=0x5865F2;

async function notifyEntry({dir,entry,stop,target,size,time,live}){
  const side=dir===1?"LONG  📈":"SHORT 📉";
  await Notify.postJSON({embeds:[{title:`🔔 ENGULF@BB — ${side}`,color:dir===1?GREEN:RED,
    description:[`**${live?"🟢 PRACTICE ORDER PLACED":"📋 DRY-RUN — enter manually"}**`,
      `**Time:** ${time} ET`,`**Entry:** ${f(entry)}`,
      `**Stop:** ${f(stop)}  (1×ATR)`,`**Target:** ${f(target)}  (3×ATR)`,
      `**Size:** ${size} MNQ`].join("\n")}]}).catch(()=>{});
}
async function notifyExit({dir,entry,exitPx,why,pnl,size,time,dayPnL,live}){
  const emoji=pnl>0?"✅":"❌";
  await Notify.postJSON({embeds:[{title:`${emoji} ENGULF@BB ${why.toUpperCase()} (${live?"LIVE":"Paper"})`,color:pnl>0?GREEN:RED,
    description:[`**${dir===1?"LONG":"SHORT"}** ${f(entry)} → ${f(exitPx)}`,
      `**P&L:** ${dol(pnl)}  (${size} MNQ)`,`**Day P&L:** ${dol(dayPnL)}`,`**Time:** ${time} ET`].join("\n")}]}).catch(()=>{});
}
async function notifyScale({dir,off,rem,lvl,realized,time,live}){
  await Notify.postJSON({embeds:[{title:`⚡ ENGULF@BB SCALE-OUT (${live?"LIVE":"Paper"})`,color:BLUE,
    description:[`**${dir===1?"LONG":"SHORT"}** hit +${SCALE_R}×ATR — took **${off}** off @ ${f(lvl)}`,
      `Banked so far: ${dol(realized)}`,`Runner: **${rem} MNQ** → stop moved to **breakeven**, target still 3×ATR`,
      `**Time:** ${time} ET`].join("\n")}]}).catch(()=>{});
}
async function notifyAlert(title,desc,color=RED){
  await Notify.postJSON({embeds:[{title,description:desc,color}]}).catch(()=>{});
}

let state=loadState(),tradeContractId=null,lastBarT=state.lastBarT||0;

async function resolveContract(){
  if(tradeContractId)return tradeContractId;
  tradeContractId=await Orders.resolveTradeContract(TRADE_SYM,PX.LIVE);
  return tradeContractId;
}

async function processLatest(){
  const et=toET(Date.now()/1000);
  writeHeartbeat({openPos:!!(state&&state.pos),dayPnL:(state&&state.dayPnL)||0,dayTrades:(state&&state.dayTrades)||0});
  if(et.dow<1||et.dow>5)return;
  let bars;
  try{bars=await PX.fetchBars({unitNumber:5,lookbackDays:10});}
  catch(e){console.error(`[${et.hhmm}] fetchBars: ${e.message}`);return;}
  if(!bars||bars.length<25){console.log(`[${et.hhmm}] Not enough bars`);return;}

  // fetchBars uses includePartialBar:false → every returned bar is already closed.
  // Do NOT drop the last one (that discarded the freshest completed bar and added ~5min of lag).
  const closed=bars;
  const last=closed[closed.length-1];
  const bet=toET(last.t);

  if(last.t<=lastBarT){console.log(`[${et.hhmm}] Bar already processed`);return;}
  lastBarT=last.t;

  // Stale guard
  if(ARMED&&(Date.now()/1000-last.t)>MAX_BAR_AGE){
    console.error(`[${et.hhmm}] STALE FEED — skip`);return;
  }

  // New day reset
  if(state.today!==bet.dk){
    if(state.today&&(state.dayTrades||0)>0){
      const msg=`Day ${state.today}: ${dol(state.dayPnL||0)} | ${state.dayTrades} trade(s)`;
      console.log(msg);
      await notifyAlert(`📊 Day Summary — ${state.today}`,msg,(state.dayPnL||0)>=0?GREEN:RED);
    }
    state={today:bet.dk,dayPnL:0,dayTrades:0,pos:null};
  }

  console.log(`[${et.hhmm}] ${bet.dk} ${bet.hhmm} close=${f(last.c)} day=${dol(state.dayPnL||0)} trades=${state.dayTrades||0}/${MAX_TR}`);

  // ── Manage open position — 2-phase: pre-scale (server OCO) → +1.5R partial → runner @ BE ──
  if(state.pos){
    const p=state.pos,lng=p.dir===1;
    const eod=bet.mins>=RTH_E||bet.dk!==p.day;
    // record a completed trade; pnl = banked partial (p.realized) + this exit leg
    const finish=async(exitPx,why,contracts,live)=>{
      const pts=lng?exitPx-p.entry:p.entry-exitPx;
      const pnl=(p.realized||0)+(pts*contracts*PV-2*contracts*FEE);
      state.dayPnL=(state.dayPnL||0)+pnl;
      audit({type:"exit",why,dir:p.dir,entry:p.entry,exitPx,pnl,size:p.size,scaled:!!p.scaled,dayPnL:state.dayPnL,live});
      console.log(`[${et.hhmm}] EXIT(${why}) @ ${f(exitPx)} | pnl=${dol(pnl)} day=${dol(state.dayPnL)} ${live?"*** LIVE ***":"(DRY-RUN)"}`);
      await notifyExit({dir:p.dir,entry:p.entry,exitPx,why,pnl,size:p.size,time:bet.hhmm,dayPnL:state.dayPnL,live});
      state.pos=null;saveState(state);
    };
    const markScaled=(off,partPx)=>{ // bank the partial leg at partPx, runner→BE
      const pts=lng?partPx-p.entry:p.entry-partPx;
      p.realized=(p.realized||0)+(pts*off*PV-2*FEE*off);
      p.rem=(p.rem||p.size)-off; p.scaled=true; if(MOVE_BE)p.stop=p.entry; saveState(state);
    };
    const reached=lng?last.h>=p.scaleLvl:last.l<=p.scaleLvl;

    if(ARMED){
      const cid=await resolveContract();
      let ps;try{ps=await Orders.searchOpenPositions(ACCOUNT_ID);}
      catch(e){console.error(`[${et.hhmm}] position poll: ${e.message}`);return;}
      const held=ps.find(x=>x.contractId===cid&&x.size!==0);
      const netSize=held?Math.abs(held.size):0;

      if(!p.scaled){
        // PRE-SCALE: server OCO (stop 1×ATR / target 3×ATR) still protects the full position.
        if(netSize===0){ // a bracket leg filled — classify it
          let px,why;
          if(lng?last.l<=p.stop:last.h>=p.stop){px=p.stop;why="stop";}
          else if(lng?last.h>=p.target:last.l<=p.target){px=p.target;why="target";}
          else{px=last.c;why="bracket-closed";}
          await finish(px,why,p.size,true);return;
        }
        if(eod){ try{await Orders.flatten(ACCOUNT_ID,cid);}catch(e){await notifyAlert("⚠️ EOD Flatten FAILED",e.message);return;} await finish(last.c,"EOD-flatten",netSize,true);return; }
        if(SCALE_ENABLED&&reached&&netSize>=2){
          const off=Math.min(netSize-1,Math.max(1,Math.round(SCALE_FRAC*p.size)));
          try{ await Orders.placeMarket({accountId:ACCOUNT_ID,contractId:cid,side:lng?Orders.SIDE.SELL:Orders.SIDE.BUY,size:off,tag:`engulf-scale-${p.day}`}); }
          catch(e){ // partial didn't fill → no state change, OCO still protects, retry next poll
            console.error(`[${et.hhmm}] partial order FAILED: ${e.message}`);
            await notifyAlert("⚠️ Scale order failed (full OCO still protecting)",e.message);return; }
          try{await Orders.cancelWorkingOrders(ACCOUNT_ID,cid);}catch(e){console.error(`[${et.hhmm}] cancel OCO: ${e.message}`);}
          markScaled(off,last.c); // record the real market fill, not the idealized +1.5R level
          console.log(`[${et.hhmm}] SCALED: ${off} off @ ~${f(p.scaleLvl)} | runner=${p.rem} stop→BE | banked=${dol(p.realized)} *** LIVE ***`);
          await notifyScale({dir:p.dir,off,rem:p.rem,lvl:p.scaleLvl,realized:p.realized,time:bet.hhmm,live:true});return;
        }
        console.log(`[${et.hhmm}] Holding full: ${lng?"LONG":"SHORT"} ${f(p.entry)} stop=${f(p.stop)} tgt=${f(p.target)} scale@${f(p.scaleLvl)}`);return;
      }
      // POST-SCALE: bot manages the runner locally (stop=BE, target=3×ATR, EOD) via market close.
      if(netSize===0){await finish(last.c,"runner-closed",p.rem,true);return;}
      let px=null,why=null;
      if(eod){px=last.c;why="EOD";}
      else if(lng?last.l<=p.stop:last.h>=p.stop){px=p.stop;why="BE-stop";}
      else if(lng?last.h>=p.target:last.l<=p.target){px=p.target;why="target";}
      if(px!=null){ try{await Orders.flatten(ACCOUNT_ID,cid);}catch(e){await notifyAlert("⚠️ Runner flatten FAILED",e.message);return;} await finish(px,why,p.rem,true); }
      else console.log(`[${et.hhmm}] Runner open: ${p.rem} ${lng?"LONG":"SHORT"} BE=${f(p.stop)} tgt=${f(p.target)}`);
      return;
    }

    // DRY-RUN: simulate the identical scale-out on bars
    if(!p.scaled){
      let px=null,why=null;
      if(eod){px=last.c;why="EOD";}
      else if(lng?last.l<=p.stop:last.h>=p.stop){px=p.stop;why="stop";}
      else if(lng?last.h>=p.target:last.l<=p.target){px=p.target;why="target";}
      if(px!=null){await finish(px,why,p.size,false);return;}
      if(SCALE_ENABLED&&reached&&p.size>=2){
        const off=Math.min(p.size-1,Math.max(1,Math.round(SCALE_FRAC*p.size)));
        markScaled(off,p.scaleLvl); // paper mirrors the backtest's limit-fill at +1.5R
        console.log(`[${et.hhmm}] WOULD SCALE: ${off} off @ ${f(p.scaleLvl)} | runner=${p.rem} stop→BE (DRY-RUN)`);
        await notifyScale({dir:p.dir,off,rem:p.rem,lvl:p.scaleLvl,realized:p.realized,time:bet.hhmm,live:false});
      } else console.log(`[${et.hhmm}] Sim holding full: ${lng?"LONG":"SHORT"} ${f(p.entry)} scale@${f(p.scaleLvl)}`);
      return;
    }
    let px=null,why=null;
    if(eod){px=last.c;why="EOD";}
    else if(lng?last.l<=p.stop:last.h>=p.stop){px=p.stop;why="BE-stop";}
    else if(lng?last.h>=p.target:last.l<=p.target){px=p.target;why="target";}
    if(px!=null)await finish(px,why,p.rem,false);
    else console.log(`[${et.hhmm}] Sim runner open: ${p.rem} BE=${f(p.stop)} tgt=${f(p.target)}`);
    return;
  }

  // ── Check for new entry ──
  if(bet.mins<TIME_FILT){console.log(`[${et.hhmm}] Before 10am — not scanning.`);return;}
  if(bet.mins>=ENTRY_CUT){console.log(`[${et.hhmm}] After 3:30pm — no new entries.`);return;}
  if((state.dayPnL||0)<=DAY_STOP){console.log(`[${et.hhmm}] Day stopped.`);return;}
  if((state.dayTrades||0)>=MAX_TR){console.log(`[${et.hhmm}] Max trades reached.`);return;}

  const sig=detectSignal(closed);
  if(!sig){console.log(`[${et.hhmm}] No signal.`);return;}

  const a=sig.atr,sp=STOP_MULT*a,tp=TGT_MULT*a;
  const sz=Math.max(1,Math.min(MAXC,Math.floor(RISK_CAP/(sp*PV))));
  const fill=sig.dir===1?sig.close+SLIP:sig.close-SLIP;
  const stop=sig.dir===1?fill-sp:fill+sp;
  const target=sig.dir===1?fill+tp:fill-tp;

  if(ARMED){
    if(isDisarmed()){
      console.log(`[${bet.hhmm}] DISARMED — signal skipped.`);
      await notifyAlert("🛑 DISARMED",`Signal fired at ${f(sig.close)} but .disarm is set — no order placed.`);
      return;
    }
    try{
      const cid=await resolveContract();
      const res=await Orders.placeBracketMarket({accountId:ACCOUNT_ID,contractId:cid,
        dir:sig.dir,size:sz,stopPts:sp,targetPts:tp,tag:`engulf-${bet.dk}-${last.t}`});
      let actualFill=fill;
      try{const ps=await Orders.searchOpenPositions(ACCOUNT_ID);
        const p=ps.find(x=>x.contractId===cid&&x.size!==0);
        if(p&&isFinite(p.averagePrice))actualFill=p.averagePrice;}catch{}
      state.pos={dir:sig.dir,entry:actualFill,stop,target,size:sz,rem:sz,day:bet.dk,
        atr:a,scaleLvl:sig.dir===1?actualFill+SCALE_R*a:actualFill-SCALE_R*a,scaled:false,realized:0};
      state.dayTrades=(state.dayTrades||0)+1;
      saveState(state);
      audit({type:"entry",dir:sig.dir,entry:actualFill,stop,target,size:sz,orderId:res.orderId,live:true});
      console.log(`[${bet.hhmm}] ENTERED ${sig.dir===1?"LONG":"SHORT"} @ ${f(actualFill)} stop=${f(stop)} tgt=${f(target)} ${sz}MNQ orderId=${res.orderId} *** LIVE ***`);
      await notifyEntry({dir:sig.dir,entry:actualFill,stop,target,size:sz,time:bet.hhmm,live:true});
    }catch(e){
      console.error(`[${bet.hhmm}] ORDER FAILED: ${e.message}`);
      await notifyAlert("🚨 ORDER FAILED",e.message);
    }
  }else{
    state.pos={dir:sig.dir,entry:fill,stop,target,size:sz,rem:sz,day:bet.dk,
      atr:a,scaleLvl:sig.dir===1?fill+SCALE_R*a:fill-SCALE_R*a,scaled:false,realized:0};
    state.dayTrades=(state.dayTrades||0)+1;
    saveState(state);
    audit({type:"entry",dir:sig.dir,entry:fill,stop,target,size:sz,live:false});
    console.log(`[${bet.hhmm}] WOULD ENTER ${sig.dir===1?"LONG":"SHORT"} @ ${f(fill)} stop=${f(stop)} tgt=${f(target)} ${sz}MNQ (DRY-RUN)`);
    await notifyEntry({dir:sig.dir,entry:fill,stop,target,size:sz,time:bet.hhmm,live:false});
  }
  saveState(state);
}

(async()=>{
  const arg=process.argv[2];
  if(arg==="--test"){
    await notifyAlert("🧪 Engulf@BB Bot — ONLINE",
      `Mode: **${ARMED?"🟢 ARMED (practice orders)":"🟡 DRY-RUN (paper)"}**\nAccount: ${ACCOUNT_ID}\nStrategy: Engulfing@BB | 10am-3:30pm ET\nStop 1xATR | Target 3xATR | $400 risk | max ${MAX_TR}/day`,BLUE);
    console.log("Test ping sent.");return;
  }
  if(arg==="--once"){await processLatest();return;}

  // ── single-instance guard: never run two copies (prevents double orders) ──
  if(anotherInstanceRunning()){
    console.error("Another live-engulfing instance is already running — exiting.");
    process.exit(0);
  }
  writeLock();
  process.on("exit",releaseLock);
  process.on("SIGINT",()=>{releaseLock();process.exit(0);});
  process.on("SIGTERM",()=>{releaseLock();process.exit(0);});

  console.log("=".repeat(60));
  console.log(`  Engulf@BB | ${ARMED?"*** ARMED — PRACTICE ORDERS ***":"DRY-RUN (paper)"}`);
  console.log(`  Account: ${ACCOUNT_ID} (Practice) | ${TRADE_SYM} | Polling every ${POLL_MS/1000}s`);
  console.log("=".repeat(60));

  if(ARMED){
    try{await resolveContract();console.log(`  Contract: ${tradeContractId}`);}
    catch(e){console.error("FATAL: contract resolve failed:",e.message);process.exit(1);}
  }
  await notifyAlert(`🟢 Practice Engulf@BB Bot STARTED`,
    `Mode: ${ARMED?"**PRACTICE ORDERS (sim)**":"Paper (no orders)"}\nAccount: ${ACCOUNT_ID}`,ARMED?RED:BLUE);

  await processLatest();
  setInterval(async()=>{try{await processLatest();}catch(e){console.error("loop:",e.message);}},POLL_MS);
})();
