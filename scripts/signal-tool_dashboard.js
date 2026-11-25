// =============================================================
//  dashboard.js — local web UI for the NQ auto-trader.
//
//  Zero npm dependencies. Reads the bot's own artifacts and (read-only) the
//  ProjectX account balance for the Combine scoreboard:
//      logs/live-signals.jsonl  — audit trail (entries / exits / errors / skips)
//      .live-state.json         — current open position (if any)
//      .live-lock               — running PID (RUNNING / STOPPED)
//      .disarm                  — kill-switch presence (ARMED vs DISARMED)
//      .heartbeat               — loop liveness (detects a hung/dead poll loop)
//      logs/charts/*.png        — per-trade entry/exit chart snapshots
//      logs/backtest.json       — latest backtest summary (if present)
//
//  Run:  node dashboard.js        (opens http://localhost:8787 in your browser)
//  Phone access: set DASH_HOST=0.0.0.0 to bind all interfaces (see PHONE-ACCESS.md).
// =============================================================
"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");
const { exec } = require("child_process");
const PX = require("./projectx"); // data-only: getAccounts() for the Combine scoreboard

const PORT = parseInt(process.env.DASH_PORT || "8787", 10);
const HOST = process.env.DASH_HOST || "127.0.0.1";
const DIR = __dirname;
const LOG = path.join(DIR, "logs", "live-signals.jsonl");
const STATE_FILE = path.join(DIR, ".live-state.json");
const LOCK_FILE = path.join(DIR, ".live-lock");
const DISARM_FILE = path.join(DIR, ".disarm");
const HEARTBEAT_FILE = path.join(DIR, ".heartbeat");
const CHART_DIR = path.join(DIR, "logs", "charts");
const BACKTEST_FILE = path.join(DIR, "logs", "backtest.json");

const ENTRY_KINDS = new Set(["ORDER_ENTRY", "INTENT_ENTRY"]);
const EXIT_KINDS = new Set(["ORDER_EXIT", "INTENT_EXIT"]);

// ---- TopStep $50K Combine constants + contract economics ----
const ACCOUNT_ID = parseInt(process.env.PROJECTX_ACCOUNT_ID || "24717879", 10);
const PV = 2;                 // MNQ = $2 / index point
const START_BALANCE = 50000;  // $50K Combine
const PROFIT_TARGET = 3000;   // +$3,000 to pass → balance $53,000
const MLL = 2000;             // $2,000 trailing max loss
const DLL = 1000;             // $1,000 daily loss limit
const HEARTBEAT_STALE_MS = 150 * 1000; // poll is 60s → flag stale past ~2.5 polls

const etDate = (s) => new Date(s * 1000).toLocaleString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" });
const etTime = (s) => new Date(s * 1000).toLocaleString("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" });
const etDayKey = (s) => new Date(s * 1000).toLocaleDateString("en-US", { timeZone: "America/New_York" });

function readAudit() {
  let text;
  try { text = fs.readFileSync(LOG, "utf8"); } catch { return []; }
  const recs = [];
  for (const line of text.split("\n")) {
    const s = line.trim();
    if (!s) continue;
    try { recs.push(JSON.parse(s)); } catch { /* skip malformed */ }
  }
  return recs;
}

// Pair each entry with the next exit (the bot only ever holds one position).
function buildTrades(recs) {
  const trades = [];
  let open = null;
  for (const r of recs) {
    if (ENTRY_KINDS.has(r.kind)) {
      open = r;
    } else if (EXIT_KINDS.has(r.kind) && open) {
      const pnl = typeof r.pnl === "number" ? r.pnl : 0;
      const pts = typeof r.pts === "number" ? r.pts : null;
      const riskPts = open.stop != null && open.entry != null ? Math.abs(open.entry - open.stop) : null;
      trades.push({
        mode: open.kind === "ORDER_ENTRY" ? "LIVE" : "DRY",
        dir: open.dir, entry: open.entry, exit: r.exit, stop: open.stop, target: open.target,
        size: open.size, pts, pnl, why: r.why,
        slippage: typeof open.slippage === "number" ? open.slippage : null,
        rMultiple: pts != null && riskPts ? pts / riskPts : null,
        entryT: open.barT, exitT: r.barT,
        holdMin: open.barT != null && r.barT != null ? Math.round((r.barT - open.barT) / 60) : null,
        win: pnl > 0,
      });
      open = null;
    }
  }
  return trades;
}

function streaks(trades) {
  let cur = 0, maxW = 0, maxL = 0;
  for (const t of trades) {
    if (t.pnl > 0) { cur = cur > 0 ? cur + 1 : 1; maxW = Math.max(maxW, cur); }
    else if (t.pnl < 0) { cur = cur < 0 ? cur - 1 : -1; maxL = Math.min(maxL, cur); }
  }
  return { current: cur, maxWin: maxW, maxLoss: Math.abs(maxL) };
}

function summarize(trades) {
  const wins = trades.filter((t) => t.pnl > 0);
  const losses = trades.filter((t) => t.pnl < 0);
  const totalPnl = trades.reduce((a, t) => a + t.pnl, 0);
  const grossWin = wins.reduce((a, t) => a + t.pnl, 0);
  const grossLoss = Math.abs(losses.reduce((a, t) => a + t.pnl, 0));
  const todayKey = new Date().toLocaleDateString("en-US", { timeZone: "America/New_York" });
  const today = trades.filter((t) => etDayKey(t.exitT) === todayKey);
  const rs = trades.map((t) => t.rMultiple).filter((r) => r != null);
  const holds = trades.map((t) => t.holdMin).filter((h) => h != null);
  const slips = trades.map((t) => t.slippage).filter((s) => s != null);
  const longs = trades.filter((t) => t.dir === 1);
  const shorts = trades.filter((t) => t.dir === -1);
  const byReason = {};
  for (const t of trades) { const k = t.why || "—"; (byReason[k] = byReason[k] || { n: 0, pnl: 0 }); byReason[k].n++; byReason[k].pnl += t.pnl; }
  const sideStat = (arr) => ({ n: arr.length, pnl: arr.reduce((a, t) => a + t.pnl, 0), wins: arr.filter((t) => t.pnl > 0).length });
  return {
    count: trades.length, wins: wins.length, losses: losses.length,
    winRate: trades.length ? Math.round((wins.length / trades.length) * 1000) / 10 : null,
    totalPnl,
    avgWin: wins.length ? grossWin / wins.length : 0,
    avgLoss: losses.length ? -grossLoss / losses.length : 0,
    profitFactor: grossLoss > 0 ? Math.round((grossWin / grossLoss) * 100) / 100 : null,
    expectancy: trades.length ? totalPnl / trades.length : 0,
    avgR: rs.length ? rs.reduce((a, b) => a + b, 0) / rs.length : null,
    avgHoldMin: holds.length ? Math.round(holds.reduce((a, b) => a + b, 0) / holds.length) : null,
    avgSlippage: slips.length ? slips.reduce((a, b) => a + b, 0) / slips.length : null,
    best: trades.length ? Math.max(...trades.map((t) => t.pnl)) : 0,
    worst: trades.length ? Math.min(...trades.map((t) => t.pnl)) : 0,
    liveCount: trades.filter((t) => t.mode === "LIVE").length,
    dryCount: trades.filter((t) => t.mode === "DRY").length,
    todayCount: today.length,
    todayPnl: today.reduce((a, t) => a + t.pnl, 0),
    streaks: streaks(trades),
    long: sideStat(longs), short: sideStat(shorts),
    byReason,
    // what-if sizing: scale realized points to 3 vs 5 MNQ (PV=$2/pt)
    whatIf3: trades.reduce((a, t) => a + (t.pts != null ? t.pts * PV * 3 : 0), 0),
    whatIf5: trades.reduce((a, t) => a + (t.pts != null ? t.pts * PV * 5 : 0), 0),
  };
}

function pidAlive(pid) {
  if (!pid) return false;
  try { process.kill(pid, 0); return true; }
  catch (e) { return e.code === "EPERM"; }
}

function readHeartbeat() {
  try {
    const hb = JSON.parse(fs.readFileSync(HEARTBEAT_FILE, "utf8"));
    const ageMs = Date.now() - new Date(hb.ts).getTime();
    return { ...hb, ageMs, stale: ageMs > HEARTBEAT_STALE_MS };
  } catch { return null; }
}

function readStatus() {
  let pid = null;
  try { pid = parseInt(fs.readFileSync(LOCK_FILE, "utf8"), 10) || null; } catch {}
  let openPos = null;
  try { openPos = (JSON.parse(fs.readFileSync(STATE_FILE, "utf8")) || {}).openPos || null; } catch {}
  let lastActivity = null;
  try { lastActivity = fs.statSync(LOG).mtime.toISOString(); } catch {}
  const disarmed = fs.existsSync(DISARM_FILE);
  let disarmReason = null;
  if (disarmed) { try { disarmReason = fs.readFileSync(DISARM_FILE, "utf8").trim().slice(0, 200); } catch {} }
  return {
    running: pidAlive(pid), pid,
    armed: !disarmed, disarmed, disarmReason,
    openPos, lastActivity,
    heartbeat: readHeartbeat(),
  };
}

// Cache the account balance: read-only, refreshed at most once a minute.
let acctCache = { at: 0, account: null, err: null };
async function getAccountCached() {
  if (Date.now() - acctCache.at < 60000 && (acctCache.account || acctCache.err)) return acctCache;
  try {
    const accounts = await PX.getAccounts();
    const account = accounts.find((a) => a.id === ACCOUNT_ID) || null;
    acctCache = { at: Date.now(), account, err: account ? null : `account ${ACCOUNT_ID} not found` };
  } catch (e) {
    acctCache = { at: Date.now(), account: acctCache.account, err: e.message };
  }
  return acctCache;
}

function combineScore(account, todayPnl) {
  if (!account || typeof account.balance !== "number") return null;
  const bal = account.balance;
  const profit = bal - START_BALANCE;
  return {
    balance: bal,
    profit,
    targetBalance: START_BALANCE + PROFIT_TARGET,
    toTarget: (START_BALANCE + PROFIT_TARGET) - bal,
    targetPct: Math.max(0, Math.min(100, Math.round((profit / PROFIT_TARGET) * 1000) / 10)),
    mll: MLL,
    dll: DLL,
    todayPnl,
    dllUsedPct: Math.max(0, Math.min(100, Math.round((-todayPnl / DLL) * 1000) / 10)),
    canTrade: account.canTrade,
    name: account.name,
  };
}

function readBacktest() {
  try { return JSON.parse(fs.readFileSync(BACKTEST_FILE, "utf8")); } catch { return null; }
}

async function buildPayload() {
  const recs = readAudit();
  const trades = buildTrades(recs);
  const summary = summarize(trades);
  const status = readStatus();
  const acct = await getAccountCached();
  const errors = recs.filter((r) => r.kind === "ORDER_ERROR").slice(-10).reverse();
  const skips = recs.filter((r) => r.kind === "DISARMED_SKIP").slice(-5).reverse();
  // equity curve: cumulative P&L in chronological order
  let cum = 0;
  const equity = trades.map((t) => ({ t: t.exitT, pnl: (cum += t.pnl) }));
  return {
    status,
    summary,
    combine: combineScore(acct.account, summary.todayPnl),
    acctErr: acct.err,
    equity,
    trades: trades.slice(-150).reverse(),
    errors, skips,
    backtest: readBacktest(),
    now: new Date().toISOString(),
  };
}

const PAGE = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NQ Auto-Trader</title>
<style>
  :root{--bg:#0b0d12;--bg2:#10131a;--card:#161a23;--card2:#1c212c;--line:#272d3a;--txt:#e8ebf2;--mut:#8b93a3;--grn:#2ecc71;--red:#e74c3c;--blu:#3aa0ff;--amb:#f1c40f;--vio:#a78bfa}
  *{box-sizing:border-box}
  html{background:#07090d}
  body{margin:0;background:transparent;color:var(--txt);font:14px/1.45 system-ui,Segoe UI,Roboto,sans-serif;min-height:100vh}
  /* WebGL smoke backdrop (ported from the spooky-smoke shader) + readability veil */
  #smoke{position:fixed;inset:0;width:100%;height:100%;display:block;z-index:-2;pointer-events:none}
  body::before{content:"";position:fixed;inset:0;background:rgba(8,10,14,.62);z-index:-1;pointer-events:none}
  .card,.score,.pos,.eq,table,dialog{backdrop-filter:blur(2px)}
  .wrap{max-width:1080px;margin:0 auto;padding:22px 18px 60px}
  .top{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:6px}
  h1{font-size:20px;margin:0;letter-spacing:.2px}
  .sub{color:var(--mut);font-size:12px;margin-bottom:16px}
  .pills{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}
  .pill{padding:6px 12px;border-radius:999px;font-weight:600;font-size:12.5px;border:1px solid var(--line);background:var(--card);white-space:nowrap}
  .pill .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;vertical-align:middle;box-shadow:0 0 8px currentColor}
  .blink{animation:bl 1.3s infinite}@keyframes bl{50%{opacity:.35}}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}
  .card{background:linear-gradient(180deg,var(--card2),var(--card));border:1px solid var(--line);border-radius:12px;padding:14px}
  .card .k{color:var(--mut);font-size:11.5px;margin-bottom:6px;text-transform:uppercase;letter-spacing:.4px}
  .card .v{font-size:23px;font-weight:750;letter-spacing:.3px}
  .card .x{font-size:11.5px;color:var(--mut);margin-top:3px}
  .score{background:linear-gradient(135deg,#171d2b,#12151d);border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:18px}
  .score h2{margin:0 0 2px;font-size:13px;color:var(--mut);text-transform:uppercase;letter-spacing:.5px}
  .score .bal{font-size:30px;font-weight:800;margin:2px 0 12px}
  .bar{height:12px;border-radius:8px;background:#0c0f15;border:1px solid var(--line);overflow:hidden;position:relative}
  .bar>span{display:block;height:100%;border-radius:8px;transition:width .5s}
  .barlbl{display:flex;justify-content:space-between;font-size:12px;color:var(--mut);margin:10px 0 4px}
  .pos{background:var(--card);border:1px solid var(--blu);border-radius:12px;padding:12px 14px;margin-bottom:18px;box-shadow:0 0 0 1px rgba(58,160,255,.15)}
  .eq{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 8px 6px;margin-bottom:18px}
  table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
  th,td{text-align:right;padding:8px 10px;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums;font-size:13px}
  th{color:var(--mut);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.3px}
  th:first-child,td:first-child{text-align:left}tr:last-child td{border-bottom:none}
  tbody tr:hover{background:rgba(255,255,255,.02)}
  .grn{color:var(--grn)}.red{color:var(--red)}.mut{color:var(--mut)}.amb{color:var(--amb)}.blu{color:var(--blu)}
  .tag{font-size:10.5px;padding:1px 6px;border-radius:5px;border:1px solid var(--line)}
  .tag.live{color:var(--red);border-color:#5a2a2a}.tag.dry{color:var(--blu);border-color:#274a6b}
  a.chart{color:var(--blu);text-decoration:none}a.chart:hover{text-decoration:underline}
  .err{background:#241316;border:1px solid #5a2a2a;border-radius:8px;padding:8px 12px;margin-top:8px;font-size:13px}
  .warn{background:#241f10;border:1px solid #5a4a1a;border-radius:8px;padding:8px 12px;margin-top:8px;font-size:13px}
  .empty{color:var(--mut);text-align:center;padding:22px}
  .ftr{color:var(--mut);font-size:11px;margin-top:22px;text-align:center}
  h2.sec{font-size:13px;color:var(--mut);margin:22px 0 8px;text-transform:uppercase;letter-spacing:.4px}
  .two{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:680px){.two{grid-template-columns:1fr}}
  dialog{background:var(--card);color:var(--txt);border:1px solid var(--line);border-radius:12px;padding:8px;max-width:92vw}
  dialog img{max-width:100%;display:block;border-radius:8px}dialog::backdrop{background:rgba(0,0,0,.7)}
</style></head><body>
<canvas id="smoke"></canvas>
<script type="x-shader/x-vertex" id="vertShader">#version 300 es
precision highp float;
in vec4 position;
void main(){gl_Position=position;}</script>
<script type="x-shader/x-fragment" id="fragShader">#version 300 es
precision highp float;
out vec4 O;
uniform float time;
uniform vec2 resolution;
uniform vec3 u_color;

#define FC gl_FragCoord.xy
#define R resolution
#define T (time+660.)

float rnd(vec2 p){p=fract(p*vec2(12.9898,78.233));p+=dot(p,p+34.56);return fract(p.x*p.y);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p),u=f*f*(3.-2.*f);return mix(mix(rnd(i),rnd(i+vec2(1,0)),u.x),mix(rnd(i+vec2(0,1)),rnd(i+1.),u.x),u.y);}
float fbm(vec2 p){float t=.0,a=1.;for(int i=0;i<5;i++){t+=a*noise(p);p*=mat2(1,-1.2,.2,1.2)*2.;a*=.5;}return t;}

void main(){
  vec2 uv=(FC-.5*R)/R.y;
  vec3 col=vec3(1);
  uv.x+=.25;
  uv*=vec2(2,1);

  float n=fbm(uv*.28-vec2(T*.01,0));
  n=noise(uv*3.+n*2.);

  col.r-=fbm(uv+vec2(0,T*.015)+n);
  col.g-=fbm(uv*1.003+vec2(0,T*.015)+n+.003);
  col.b-=fbm(uv*1.006+vec2(0,T*.015)+n+.006);

  col=mix(col, u_color, dot(col,vec3(.21,.71,.07)));

  col=mix(vec3(.08),col,min(time*.1,1.));
  col=clamp(col,.08,1.);
  O=vec4(col,1);
}</script>
<div class="wrap">
  <div class="top"><h1>🟩 NQ Auto-Trader</h1><div class="sub" id="clock"></div></div>
  <div class="sub" id="sub">loading…</div>
  <div class="pills" id="pills"></div>
  <div id="scoreWrap"></div>
  <div id="posWrap"></div>
  <div class="grid" id="cards"></div>
  <div class="eq"><div style="color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.4px;padding:0 8px 4px">Equity curve (cumulative P&L)</div><div id="eqWrap"></div></div>
  <div class="two">
    <div><h2 class="sec">By side</h2><div id="sideWrap"></div></div>
    <div><h2 class="sec">By exit reason</h2><div id="reasonWrap"></div></div>
  </div>
  <h2 class="sec">All trades</h2><div id="tradesWrap"></div>
  <h2 class="sec" style="color:var(--grn)">✅ Won trades</h2><div id="wonWrap"></div>
  <h2 class="sec" style="color:var(--red)">❌ Lost trades</h2><div id="lostWrap"></div>
  <div id="btWrap"></div>
  <div id="issues"></div>
  <div class="ftr" id="ftr"></div>
</div>
<dialog id="dlg"><img id="dlgImg" alt="trade chart"><div style="text-align:center;padding:6px"><button onclick="document.getElementById('dlg').close()">close</button></div></dialog>
<script>
/* Smoke backdrop — vanilla WebGL2 port of the spooky-smoke React component.
   Same shader; tinted dark-emerald to match the trading theme. Decorative,
   pointer-events:none, capped DPR for full-screen perf. */
(function(){
  var canvas=document.getElementById("smoke");
  var gl=canvas&&canvas.getContext("webgl2");
  if(!gl){ if(canvas) canvas.style.display="none"; return; }   // graceful fallback to flat bg
  var COLOR=[0.122,0.561,0.373]; // #1f8f5f
  function compile(type,src){var s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);
    if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))console.error("smoke shader:",gl.getShaderInfoLog(s));return s;}
  var prog=gl.createProgram();
  gl.attachShader(prog,compile(gl.VERTEX_SHADER,document.getElementById("vertShader").textContent));
  gl.attachShader(prog,compile(gl.FRAGMENT_SHADER,document.getElementById("fragShader").textContent));
  gl.linkProgram(prog);
  if(!gl.getProgramParameter(prog,gl.LINK_STATUS)){console.error("smoke link:",gl.getProgramInfoLog(prog));canvas.style.display="none";return;}
  var buf=gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER,buf);
  gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,1,-1,-1,1,1,1,-1]),gl.STATIC_DRAW);
  var pos=gl.getAttribLocation(prog,"position");
  gl.enableVertexAttribArray(pos);
  gl.vertexAttribPointer(pos,2,gl.FLOAT,false,0,0);
  var uRes=gl.getUniformLocation(prog,"resolution"),uTime=gl.getUniformLocation(prog,"time"),uCol=gl.getUniformLocation(prog,"u_color");
  function resize(){var dpr=Math.min(2,Math.max(1,window.devicePixelRatio||1));canvas.width=Math.floor(innerWidth*dpr);canvas.height=Math.floor(innerHeight*dpr);gl.viewport(0,0,canvas.width,canvas.height);}
  resize(); window.addEventListener("resize",resize);
  function loop(now){
    if(!gl.isProgram(prog))return;
    gl.clearColor(0,0,0,1); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(prog); gl.bindBuffer(gl.ARRAY_BUFFER,buf);
    gl.uniform2f(uRes,canvas.width,canvas.height);
    gl.uniform1f(uTime,now*1e-3);
    gl.uniform3fv(uCol,COLOR);
    gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
})();
</script>
<script>
const fmt=(n,d=2)=>n==null||!isFinite(n)?"—":Number(n).toFixed(d);
const money=n=>n==null||!isFinite(n)?"—":(n>=0?"+$":"-$")+Math.abs(n).toFixed(0);
const cls=n=>n>0?"grn":n<0?"red":"mut";
function pill(txt,color,blink){return '<span class="pill"><span class="dot'+(blink?' blink':'')+'" style="background:'+color+';color:'+color+'"></span>'+txt+'</span>';}
function plainPill(txt){return '<span class="pill mut">'+txt+'</span>';}
function bar(pct,color){return '<div class="bar"><span style="width:'+Math.max(0,Math.min(100,pct))+'%;background:'+color+'"></span></div>';}
function showChart(src){const d=document.getElementById('dlg');document.getElementById('dlgImg').src=src;d.showModal();}
function tradeRow(t){
  const side=t.dir===1?"LONG":(t.dir===-1?"SHORT":(t.dir||"—"));
  const ent='<a class="chart" href="#" onclick="showChart(\\''+'/charts/'+t.entryT+'-ENTRY.png\\');return false">'+fmt(t.entry)+'</a>';
  const ex='<a class="chart" href="#" onclick="showChart(\\''+'/charts/'+t.exitT+'-EXIT.png\\');return false">'+fmt(t.exit)+'</a>';
  return '<tr><td>'+t._date+' '+t._time+'</td><td>'+side+'</td>'+
    '<td><span class="tag '+(t.mode==="LIVE"?"live":"dry")+'">'+t.mode+'</span></td><td>'+ent+'</td><td>'+ex+'</td>'+
    '<td class="'+cls(t.pts)+'">'+fmt(t.pts)+'</td><td class="mut">'+fmt(t.rMultiple,2)+'R</td>'+
    '<td class="mut">'+(t.holdMin==null?"—":t.holdMin+"m")+'</td>'+
    '<td class="'+cls(t.pnl)+'">'+money(t.pnl)+'</td><td class="mut">'+(t.why||"")+'</td></tr>';
}
function tradeTable(list,emptyMsg){
  if(!list.length) return '<div class="card empty">'+emptyMsg+'</div>';
  let rows='<table><thead><tr><th>Date</th><th>Side</th><th>Mode</th><th>Entry</th><th>Exit</th><th>Pts</th><th>R</th><th>Hold</th><th>P&L</th><th>Why</th></tr></thead><tbody>';
  for(const t of list) rows+=tradeRow(t);
  return rows+'</tbody></table>';
}
function equitySvg(eq){
  if(!eq.length) return '<div class="empty">No completed trades yet — the curve appears after the first exit.</div>';
  const W=1040,H=180,P=8;const xs=eq.map((e,i)=>i),ys=eq.map(e=>e.pnl);
  const minY=Math.min(0,...ys),maxY=Math.max(0,...ys),span=(maxY-minY)||1;
  const X=i=>P+(eq.length===1?W/2:(i/(eq.length-1))*(W-2*P));
  const Y=v=>H-P-((v-minY)/span)*(H-2*P);
  let d='';eq.forEach((e,i)=>{d+=(i?'L':'M')+X(i).toFixed(1)+' '+Y(e.pnl).toFixed(1)+' ';});
  const last=eq[eq.length-1].pnl,col=last>=0?'#2ecc71':'#e74c3c';
  const zeroY=Y(0).toFixed(1);
  const area=d+'L'+X(eq.length-1).toFixed(1)+' '+zeroY+' L'+X(0).toFixed(1)+' '+zeroY+' Z';
  return '<svg viewBox="0 0 '+W+' '+H+'" width="100%" height="180" preserveAspectRatio="none">'+
    '<line x1="'+P+'" y1="'+zeroY+'" x2="'+(W-P)+'" y2="'+zeroY+'" stroke="#2a3140" stroke-dasharray="4 4"/>'+
    '<path d="'+area+'" fill="'+col+'" opacity="0.10"/>'+
    '<path d="'+d+'" fill="none" stroke="'+col+'" stroke-width="2"/>'+
    '<circle cx="'+X(eq.length-1)+'" cy="'+Y(last)+'" r="3.5" fill="'+col+'"/></svg>';
}
function miniTable(rows){
  let h='<table>';for(const r of rows){h+='<tr><td>'+r[0]+'</td>'+r.slice(1).map(c=>'<td class="'+(c&&c.cls||'')+'">'+(c&&c.v!=null?c.v:c)+'</td>').join('')+'</tr>';}return h+'</table>';
}
async function tick(){
  let d; try{ d=await (await fetch("/api/stats")).json(); }catch(e){ document.getElementById("sub").textContent="dashboard server unreachable"; return; }
  const s=d.status, sm=d.summary, hb=s.heartbeat;
  document.getElementById("clock").textContent=new Date(d.now).toLocaleString();
  document.getElementById("sub").textContent="auto-refreshing every 5s";
  // pills
  let p="";
  p+= s.running ? pill("RUNNING (pid "+s.pid+")","#2ecc71") : pill("STOPPED","#e74c3c",true);
  if(hb){ p+= hb.stale ? pill("HEARTBEAT STALE ("+Math.round(hb.ageMs/1000)+"s)","#f1c40f",true) : pill("heartbeat "+Math.round(hb.ageMs/1000)+"s ago","#2ecc71"); }
  else { p+= plainPill("no heartbeat yet"); }
  p+= s.disarmed ? pill("DISARMED (dry-run)","#f1c40f") : pill("ARMED — live orders","#e74c3c");
  document.getElementById("pills").innerHTML=p;
  // combine scoreboard
  const sw=document.getElementById("scoreWrap");
  if(d.combine){const c=d.combine;
    sw.innerHTML='<div class="score"><h2>TopStep $50K Combine — '+(c.name||'')+(c.canTrade?'':' · <span class="red">cannot trade</span>')+'</h2>'+
      '<div class="bal">$'+c.balance.toLocaleString()+' <span style="font-size:14px" class="'+cls(c.profit)+'">('+money(c.profit)+')</span></div>'+
      '<div class="barlbl"><span>Profit target +$'+PROFIT_TARGET_JS+'</span><span>'+c.targetPct+'% · '+money(c.toTarget)+' to go</span></div>'+
      bar(c.targetPct,'linear-gradient(90deg,#2ecc71,#27e0a0)')+
      '<div class="barlbl"><span>Daily loss limit ($'+c.dll+')</span><span>'+(c.todayPnl<0?money(c.todayPnl)+' today · '+c.dllUsedPct+'% used':'no loss today')+'</span></div>'+
      bar(c.dllUsedPct,'linear-gradient(90deg,#f1c40f,#e74c3c)')+
      '<div class="x" style="color:var(--mut);font-size:11px;margin-top:10px">Trailing max loss $'+c.mll+' tracks your peak balance — keep cushion above it. Balance via ProjectX (read-only), cached ~60s.</div></div>';
  } else { sw.innerHTML = d.acctErr ? '<div class="warn">Combine balance unavailable: '+d.acctErr+'</div>' : ''; }
  // open position
  const pw=document.getElementById("posWrap");
  if(s.openPos){const o=s.openPos;const side=o.dir===1?"LONG":"SHORT";
    pw.innerHTML='<div class="pos"><b>● Open position:</b> '+side+' '+(o.live?'<span class="tag live">LIVE</span>':'<span class="tag dry">sim</span>')+' · entry '+fmt(o.entry)+' · stop '+fmt(o.stop)+' · target '+fmt(o.target)+(o.adopted?' · <span class="amb">adopted</span>':'')+'</div>';
  } else pw.innerHTML='';
  // KPI cards
  const wr=sm.winRate==null?"—":sm.winRate+"%";
  const st=sm.streaks;
  const cards=[
    ["Trades", sm.count+'', sm.liveCount+' live · '+sm.dryCount+' dry'],
    ["Win rate", wr, sm.wins+'W · '+sm.losses+'L'],
    ["Total P&L", money(sm.totalPnl), 'PF '+(sm.profitFactor==null?"—":sm.profitFactor), cls(sm.totalPnl)],
    ["Today P&L", money(sm.todayPnl), sm.todayCount+' trade(s)', cls(sm.todayPnl)],
    ["Expectancy", money(sm.expectancy), 'avg '+(sm.avgR==null?"—":fmt(sm.avgR,2)+'R')+'/trade'],
    ["Avg W / L", money(sm.avgWin)+' / '+money(sm.avgLoss), 'best '+money(sm.best)+' · worst '+money(sm.worst)],
    ["Streak", (st.current>0?'+'+st.current+'W':(st.current<0?st.current+'L':'—')), 'max '+st.maxWin+'W / '+st.maxLoss+'L'],
    ["Avg hold", sm.avgHoldMin==null?"—":sm.avgHoldMin+'m', sm.avgSlippage==null?'':'slip '+fmt(sm.avgSlippage,2)+'pt'],
    ["What-if @3 / @5", money(sm.whatIf3)+' / '+money(sm.whatIf5), 'same signals, diff size'],
  ];
  document.getElementById("cards").innerHTML=cards.map(c=>'<div class="card"><div class="k">'+c[0]+'</div><div class="v '+(c[3]||"")+'">'+c[1]+'</div><div class="x">'+(c[2]||"")+'</div></div>').join("");
  // equity curve
  document.getElementById("eqWrap").innerHTML=equitySvg(d.equity);
  // by side
  const sd=(lbl,x)=>[lbl,{v:x.n+'',cls:'mut'},{v:x.n?Math.round(x.wins/x.n*100)+'%':'—',cls:'mut'},{v:money(x.pnl),cls:cls(x.pnl)}];
  document.getElementById("sideWrap").innerHTML='<table><thead><tr><th>Side</th><th>N</th><th>Win%</th><th>P&L</th></tr></thead><tbody>'+
    [sd('Long',sm.long),sd('Short',sm.short)].map(r=>'<tr><td>'+r[0]+'</td><td class="'+r[1].cls+'">'+r[1].v+'</td><td class="'+r[2].cls+'">'+r[2].v+'</td><td class="'+r[3].cls+'">'+r[3].v+'</td></tr>').join('')+'</tbody></table>';
  // by reason
  const rk=Object.keys(sm.byReason);
  document.getElementById("reasonWrap").innerHTML=rk.length?('<table><thead><tr><th>Reason</th><th>N</th><th>P&L</th></tr></thead><tbody>'+
    rk.map(k=>'<tr><td>'+k+'</td><td class="mut">'+sm.byReason[k].n+'</td><td class="'+cls(sm.byReason[k].pnl)+'">'+money(sm.byReason[k].pnl)+'</td></tr>').join('')+'</tbody></table>'):'<div class="card empty">No exits yet.</div>';
  // trade tables
  document.getElementById("tradesWrap").innerHTML=tradeTable(d.trades,"No completed trades yet. The bot trades the power hour (3:00–3:45 PM ET).");
  document.getElementById("wonWrap").innerHTML=tradeTable(d.trades.filter(t=>t.pnl>0),"No winning trades yet.");
  document.getElementById("lostWrap").innerHTML=tradeTable(d.trades.filter(t=>t.pnl<0),"No losing trades yet.");
  // backtest
  const bw=document.getElementById("btWrap");
  if(d.backtest){const b=d.backtest;
    bw.innerHTML='<h2 class="sec">🧪 Backtest ('+(b.bars||'?')+' bars · '+(b.from||'')+'→'+(b.to||'')+')</h2>'+
      '<div class="grid">'+[
        ['Trades',(b.n||0)+''],['Win rate',(b.winRate!=null?b.winRate+'%':'—')],['Net pts',fmt(b.netPts,1)],
        ['Profit factor',(b.pf!=null?b.pf:'—')+''],['Max DD pts',fmt(b.ddPts,1)],['Worst day pts',fmt(b.worstDayPts,1)],
        ['Net @5 MNQ',money(b.netPts!=null?b.netPts*2*5:null)],['Max loss streak',(b.maxLossStreak||0)+''],['Expectancy pts',fmt(b.expectancyPts,2)]
      ].map(c=>'<div class="card"><div class="k">'+c[0]+'</div><div class="v">'+c[1]+'</div></div>').join('')+'</div>'+
      '<div class="sub">Generated '+(b.generatedAt?new Date(b.generatedAt).toLocaleString():'?')+' by backtest.js — gated power-hour + ADX>'+(b.adxGate||20)+', same rules as live.</div>';
  } else bw.innerHTML='';
  // issues
  let iss="";
  if(s.disarmed){ iss+='<div class="warn"><b>⚠️ Kill-switch active.</b> '+(s.disarmReason||'.disarm present')+' — delete .disarm to re-arm.</div>'; }
  if(d.errors.length){ iss+='<h2 class="sec">Recent errors</h2>'; for(const e of d.errors){ iss+='<div class="err">'+new Date(e.ts).toLocaleString()+' · '+(e.phase||"")+': '+(e.error||"")+'</div>'; } }
  if(d.skips.length){ iss+='<h2 class="sec">Disarmed skips</h2>'; for(const k of d.skips){ iss+='<div class="warn">'+new Date(k.ts).toLocaleString()+' · skipped '+(k.dir||"")+' entry (kill-switch)</div>'; } }
  document.getElementById("issues").innerHTML=iss;
  document.getElementById("ftr").textContent="NQ power-hour + ADX>20 @ 5 MNQ · acct "+ACCOUNT_ID_JS+" · reads logs/live-signals.jsonl";
}
const PROFIT_TARGET_JS=${PROFIT_TARGET}, ACCOUNT_ID_JS=${ACCOUNT_ID};
tick(); setInterval(tick,5000);
</script></body></html>`;

const server = http.createServer(async (req, res) => {
  // serve per-trade chart snapshots (read-only, sanitized to logs/charts)
  if (req.url.startsWith("/charts/")) {
    const name = path.basename(decodeURIComponent(req.url.split("?")[0]));
    const file = path.join(CHART_DIR, name);
    if (!file.startsWith(CHART_DIR) || !/^[\w.\-]+\.png$/.test(name)) { res.writeHead(400); res.end("bad"); return; }
    fs.readFile(file, (err, buf) => {
      if (err) { res.writeHead(404, { "Content-Type": "text/plain" }); res.end("no chart for this bar yet"); return; }
      res.writeHead(200, { "Content-Type": "image/png", "Cache-Control": "max-age=300" });
      res.end(buf);
    });
    return;
  }
  if (req.url.startsWith("/api/stats")) {
    try {
      const payload = await buildPayload();
      payload.trades = payload.trades.map((t) => ({ ...t, _date: etDate(t.exitT), _time: etTime(t.exitT) }));
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(payload));
    } catch (e) {
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: e.message }));
    }
    return;
  }
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
  res.end(PAGE);
});

server.listen(PORT, HOST, () => {
  const url = `http://localhost:${PORT}`;
  console.log(`NQ dashboard running at http://${HOST}:${PORT}  (Ctrl+C to stop)`);
  if (HOST === "127.0.0.1") exec(`cmd /c start "" "${url}"`, () => {}); // best-effort browser open
});
