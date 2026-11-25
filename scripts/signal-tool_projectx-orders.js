// =============================================================
//  projectx-orders.js — ProjectX (TopstepX) ORDER EXECUTION layer.
//
//  *** THIS MODULE PLACES REAL ORDERS. *** It is the deliberately-armed
//  counterpart to the data-only projectx.js. Nothing here runs unless the
//  caller (live-signal.js) is explicitly ARMED. Compliance: TopStep permits API
//  automation on evaluation/Combine accounts (barred on Live Funded) — keep this
//  pointed at the eval account only.
//
//  Verified against gateway.docs.projectx.com (base https://api.topstepx.com):
//    POST /api/Order/place           — type 2=Market, side 0=buy/1=sell, with
//                                       stopLossBracket/takeProfitBracket {ticks,type}
//    POST /api/Position/searchOpen   — { accountId } -> { positions:[...] }
//    POST /api/Position/closeContract— { accountId, contractId } (flatten)
//    POST /api/Order/searchOpen      — { accountId } -> { orders:[...] }
//    POST /api/Order/cancel          — { accountId, orderId }
//    POST /api/Contract/search       — { searchText, live } -> { contracts:[...] }
//
//  Order/bracket type enums: 1=Limit, 2=Market, 4=Stop. Side: 0=Bid(buy), 1=Ask(sell).
//  NQ/MNQ tick = 0.25 index pts, so ticks = round(points / 0.25).
// =============================================================
"use strict";

const PX = require("./projectx.js");

const TICK = 0.25;                 // NQ/MNQ minimum price increment (index points)
const TYPE = { LIMIT: 1, MARKET: 2, STOP: 4 };
const SIDE = { BUY: 0, SELL: 1 };

const ptsToTicks = (pts) => Math.max(1, Math.round(Math.abs(pts) / TICK));

// authed POST that reuses projectx.js's token cache + base URL (keeps creds in one place)
async function api(pathName, body) {
  const token = await PX.authToken();
  const r = await fetch(`${PX.BASE}${pathName}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || j.success === false) {
    throw new Error(`ProjectX ${pathName} failed: HTTP ${r.status} errorCode=${j.errorCode} ${j.errorMessage || ""}`);
  }
  return j;
}

// resolve the TRADABLE front-month contract for a symbol (independent of the data
// client's cache, since we trade MNQ specifically). live=false for sim/eval data.
async function resolveTradeContract(searchText, live = false) {
  const j = await api("/api/Contract/search", { searchText, live });
  const list = j.contracts || [];
  if (!list.length) throw new Error(`ProjectX: no tradable contract for "${searchText}"`);
  return list[0].id;
}

// Place a MARKET entry with server-side OCO bracket (stop + target), atomically.
// dir: 1=long, -1=short. stopPts/targetPts are POINT distances from entry.
//
// ProjectX bracket `ticks` are a SIGNED offset from the entry fill:
//   long  -> stop BELOW (negative), target ABOVE (positive)
//   short -> stop ABOVE (positive), target BELOW (negative)
async function placeBracketMarket({ accountId, contractId, dir, size, stopPts, targetPts, tag }) {
  const long = dir === 1;
  const stopTicks = (long ? -1 : 1) * ptsToTicks(stopPts);
  const targetTicks = (long ? 1 : -1) * ptsToTicks(targetPts);
  const body = {
    accountId, contractId,
    type: TYPE.MARKET,
    side: long ? SIDE.BUY : SIDE.SELL,
    size,
    stopLossBracket: { ticks: stopTicks, type: TYPE.STOP },
    takeProfitBracket: { ticks: targetTicks, type: TYPE.LIMIT },
    customTag: tag,
  };
  const j = await api("/api/Order/place", body);
  return { orderId: j.orderId, raw: j };
}

// Plain MARKET order with NO brackets — used to SCALE OUT of (reduce) a position.
// side: 0=buy, 1=sell (pass the OPPOSITE of the entry side to reduce a position).
async function placeMarket({ accountId, contractId, side, size, tag }) {
  const j = await api("/api/Order/place", {
    accountId, contractId, type: TYPE.MARKET, side, size, customTag: tag,
  });
  return { orderId: j.orderId, raw: j };
}

// Cancel only the working bracket/stop/target legs for a contract, WITHOUT closing
// the position (unlike flatten). Used after a partial scale-out to drop the stale
// full-size OCO so it can't over-fill and flip the reduced position.
async function cancelWorkingOrders(accountId, contractId) {
  let cancelled = 0;
  const orders = await searchOpenOrders(accountId);
  for (const o of orders.filter((o) => o.contractId === contractId)) {
    try { await cancelOrder(accountId, o.id); cancelled++; } catch { /* best effort */ }
  }
  return cancelled;
}

async function searchOpenPositions(accountId) {
  const j = await api("/api/Position/searchOpen", { accountId });
  return j.positions || [];
}

async function searchOpenOrders(accountId) {
  const j = await api("/api/Order/searchOpen", { accountId });
  return j.orders || [];
}

// Realized trades (half-turns) in a time window. Each trade carries the broker's
// own `profitAndLoss` (USD, populated on the closing half-turn; null on the
// opener) and `fees` — the authoritative "how much did I make/lose" figure.
async function searchTrades(accountId, startTimestamp, endTimestamp) {
  const j = await api("/api/Trade/search", { accountId, startTimestamp, endTimestamp });
  return j.trades || [];
}

// Sum realized P&L + fees for one contract over a window. Returns null pnl if the
// endpoint gave us nothing usable, so callers can degrade gracefully.
async function realizedPnL(accountId, contractId, startTimestamp, endTimestamp) {
  const trades = await searchTrades(accountId, startTimestamp, endTimestamp);
  const mine = trades.filter((t) => t.contractId === contractId && !t.voided);
  if (!mine.length) return { pnl: null, fees: 0, count: 0 };
  const pnl = mine.reduce((s, t) => s + (Number(t.profitAndLoss) || 0), 0);
  const fees = mine.reduce((s, t) => s + (Number(t.fees) || 0), 0);
  const hasPnl = mine.some((t) => t.profitAndLoss != null);
  return { pnl: hasPnl ? pnl : null, fees, count: mine.length };
}

async function closeContract(accountId, contractId) {
  return api("/api/Position/closeContract", { accountId, contractId });
}

async function cancelOrder(accountId, orderId) {
  return api("/api/Order/cancel", { accountId, orderId });
}

// Flatten everything for one contract: market-close the position, then cancel any
// leftover working bracket legs so nothing can re-open the position later.
async function flatten(accountId, contractId) {
  const result = { closed: false, cancelled: 0, errors: [] };
  try {
    const positions = await searchOpenPositions(accountId);
    if (positions.some((p) => p.contractId === contractId && p.size !== 0)) {
      await closeContract(accountId, contractId); result.closed = true;
    }
  } catch (e) { result.errors.push("close: " + e.message); }
  try {
    const orders = await searchOpenOrders(accountId);
    for (const o of orders.filter((o) => o.contractId === contractId)) {
      try { await cancelOrder(accountId, o.id); result.cancelled++; } catch (e) { result.errors.push("cancel " + o.id + ": " + e.message); }
    }
  } catch (e) { result.errors.push("searchOrders: " + e.message); }
  return result;
}

module.exports = {
  TICK, TYPE, SIDE, ptsToTicks,
  resolveTradeContract, placeBracketMarket, placeMarket, cancelWorkingOrders,
  searchOpenPositions, searchOpenOrders, closeContract, cancelOrder, flatten,
  searchTrades, realizedPnL,
};
