// =============================================================
//  yahoo.js — Yahoo Finance free historical bars. DATA-ONLY.
//
//  *** DATA ONLY. *** No auth, no account, no orders — just a public
//  read of the Yahoo chart API. Used as a FREE deeper-history source for
//  backtesting when ProjectX/TopStep sim history (~12 days) is too shallow.
//
//  Yahoo caps intraday history at ~60 days for sub-daily intervals, which
//  is why 5m range=60d returns ~58 trading days of NQ futures (NQ=F).
//
//  Returns ASCENDING [{ t:unixSec, o,h,l,c,v }] — same shape as projectx.js
//  fetchBars, so it drops straight into the mean-rev engine / exit sim.
//
//  Self-test:  node yahoo.js --test
//  Docs (unofficial): https://query1.finance.yahoo.com/v8/finance/chart/NQ%3DF
// =============================================================
"use strict";

const SYMBOL = process.env.YAHOO_SYMBOL || "NQ=F"; // Nasdaq-100 front-month future
const BASE = "https://query1.finance.yahoo.com/v8/finance/chart";

// Pull historical bars. interval e.g. "5m"; range e.g. "60d" (Yahoo's intraday cap).
async function fetchBars({ interval = "5m", range = "60d", symbol = SYMBOL } = {}) {
  const url = `${BASE}/${encodeURIComponent(symbol)}?interval=${interval}&range=${range}`;
  const r = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
  if (!r.ok) throw new Error(`Yahoo HTTP ${r.status} for ${symbol}`);
  const j = await r.json();
  const res = j.chart && j.chart.result && j.chart.result[0];
  if (!res) {
    const msg = (j.chart && j.chart.error && j.chart.error.description) || "no result";
    throw new Error(`Yahoo: ${msg}`);
  }
  const ts = res.timestamp || [];
  const q = (res.indicators && res.indicators.quote && res.indicators.quote[0]) || {};
  const bars = [];
  for (let i = 0; i < ts.length; i++) {
    // Yahoo pads non-trading slots with nulls — skip incomplete bars.
    if (q.open[i] == null || q.high[i] == null || q.low[i] == null || q.close[i] == null) continue;
    bars.push({ t: ts[i], o: q.open[i], h: q.high[i], l: q.low[i], c: q.close[i], v: q.volume[i] == null ? 0 : q.volume[i] });
  }
  bars.sort((a, b) => a.t - b.t);
  return bars;
}

module.exports = { fetchBars, SYMBOL, BASE };

// ---- CLI self-test: node yahoo.js --test ----
if (require.main === module && process.argv[2] === "--test") {
  (async () => {
    try {
      const bars = await fetchBars({ interval: "5m", range: "60d" });
      const days = new Set(
        bars.map((b) => new Date(b.t * 1000).toLocaleDateString("en-US", { timeZone: "America/New_York" }))
      ).size;
      const fmt = (t) => new Date(t * 1000).toLocaleDateString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" });
      console.log(`Yahoo ${SYMBOL}: ${bars.length} valid 5m bars over ${days} ET days (${fmt(bars[0].t)} .. ${fmt(bars[bars.length - 1].t)}). Last 3:`);
      for (const b of bars.slice(-3)) {
        const et = new Date(b.t * 1000).toLocaleString("en-US", { timeZone: "America/New_York" });
        console.log(`  ${et}  O ${b.o}  H ${b.h}  L ${b.l}  C ${b.c}  V ${b.v}`);
      }
      console.log("\nData-only self-test passed. No orders, no auth.");
    } catch (e) {
      console.error("Self-test FAILED:", e.message);
      process.exit(1);
    }
  })();
}
