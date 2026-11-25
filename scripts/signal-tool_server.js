// =============================================================
//  server.js — tiny zero-dependency Node server for the NQ Signal Tool.
//  Responsibilities:
//    1. Serve the static panel from /public
//    2. Proxy market data (dodges browser CORS on Yahoo's endpoint)
//
//  The data layer is behind a DataSource interface so the official
//  ProjectX / TopstepX feed can be dropped in later WITHOUT touching
//  the front-end: implement getBars() and set ACTIVE_SOURCE.
//
//  Run:  node server.js   ->   http://localhost:5173
// =============================================================
"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = process.env.PORT || 5173;
const PUBLIC_DIR = path.join(__dirname, "public");
const SYMBOL = process.env.SYMBOL || "NQ=F"; // E-mini Nasdaq-100 front month

// ---- DataSource interface --------------------------------------------------
// getBars({ interval, range }) -> { meta, bars: [{t,o,h,l,c,v}] }
//   interval: "5m" | "1d" etc.   range: "5d" | "3mo" etc.
//   t = epoch SECONDS. OHLCV are floats. Nulls are dropped.

const YahooDataSource = {
  name: "yahoo",
  async getBars({ interval, range }) {
    const url =
      `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(SYMBOL)}` +
      `?interval=${encodeURIComponent(interval)}&range=${encodeURIComponent(range)}`;
    const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
    if (!res.ok) throw new Error("yahoo " + res.status);
    const json = await res.json();
    const result = json?.chart?.result?.[0];
    if (!result) throw new Error("yahoo: empty result");
    const ts = result.timestamp || [];
    const q = result.indicators?.quote?.[0] || {};
    const bars = [];
    for (let i = 0; i < ts.length; i++) {
      const o = q.open?.[i], h = q.high?.[i], l = q.low?.[i], c = q.close?.[i];
      if (o == null || h == null || l == null || c == null) continue;
      bars.push({ t: ts[i], o, h, l, c, v: q.volume?.[i] ?? 0 });
    }
    return {
      meta: {
        symbol: result.meta?.symbol,
        price: result.meta?.regularMarketPrice,
        tz: result.meta?.exchangeTimezoneName,
        source: "yahoo (delayed)",
      },
      bars,
    };
  },
};

// FUTURE: implement getBars() against the ProjectX REST history endpoint
// (key -> JWT -> /history/retrieveBars) and switch ACTIVE_SOURCE to it.
const ACTIVE_SOURCE = YahooDataSource;

// ---- HTTP server -----------------------------------------------------------
const MIME = {
  ".html": "text/html", ".js": "text/javascript",
  ".css": "text/css", ".json": "application/json",
};

function sendJSON(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { "Content-Type": "application/json", "Cache-Control": "no-store" });
  res.end(body);
}

function serveStatic(req, res) {
  let rel = req.url.split("?")[0];
  if (rel === "/") rel = "/index.html";
  const filePath = path.join(PUBLIC_DIR, path.normalize(rel));
  if (!filePath.startsWith(PUBLIC_DIR)) { res.writeHead(403); return res.end("forbidden"); }
  fs.readFile(filePath, (err, data) => {
    if (err) { res.writeHead(404); return res.end("not found"); }
    res.writeHead(200, { "Content-Type": MIME[path.extname(filePath)] || "text/plain" });
    res.end(data);
  });
}

async function handleBars(req, res, defaults) {
  try {
    const u = new URL(req.url, `http://localhost:${PORT}`);
    const interval = u.searchParams.get("interval") || defaults.interval;
    const range = u.searchParams.get("range") || defaults.range;
    const data = await ACTIVE_SOURCE.getBars({ interval, range });
    sendJSON(res, 200, data);
  } catch (e) {
    sendJSON(res, 502, { error: String(e.message || e) });
  }
}

const server = http.createServer((req, res) => {
  const route = req.url.split("?")[0];
  if (route === "/api/bars") return handleBars(req, res, { interval: "5m", range: "5d" });
  if (route === "/api/daily") return handleBars(req, res, { interval: "1d", range: "3mo" });
  return serveStatic(req, res);
});

server.listen(PORT, () => {
  console.log(`NQ Signal Tool running:  http://localhost:${PORT}`);
  console.log(`Data source: ${ACTIVE_SOURCE.name}  symbol: ${SYMBOL}`);
});
