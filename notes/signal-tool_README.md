# NQ Signal Tool (v5) — standalone

A simple decision-support panel that runs the **v5 BEST** strategy logic on
**NQ** (Nasdaq-100 futures) and tells you, in plain numbers, whether to
**BUY / SELL / WAIT**, plus the **entry, stop, and target**.

This is the standalone first step toward the TopstepX browser extension. The
strategy math (`public/indicators.js`, `public/signal.js`) is framework-free and
ports directly into the extension content script later. The data layer in
`server.js` is behind a `DataSource` interface so the **official ProjectX /
TopstepX feed drops in** once you have a funded account + API key — no front-end
changes needed.

## Run it

```
cd daytrading-automation/signal-tool
node server.js
```

Then open **http://localhost:5173** in your browser.

- Stop the server: `Ctrl+C`.
- Change port/symbol: `PORT=8080 SYMBOL=NQ=F node server.js`.

## ⚠️ Read this before trusting a number

- **Data is DELAYED ~10 min** (free Yahoo feed). This tool is for **practice /
  paper-trading and validating the signal logic** — NOT live execution.
- It is **decision support only**. You place every order yourself. (This also
  keeps it TopStep-compliant — no automation.)
- The panel evaluates the **latest closed 5-min bar**. A `BUY`/`SELL` only
  appears during RTH (09:30–16:00 ET) when every v5 condition lines up.

## The locked config (matches TradingView v5 BEST)

| Setting | Value |
|---|---|
| Timeframe | 5-min |
| MACD cross lookback | 2 bars |
| RSI long floor | 60 |
| RSI short ceiling | 32 |
| Bollinger | 12 / 2.0 |
| MACD | 12 / 26 / 9 |
| RSI | 7 |
| ADX regime | > 20 |
| Trend filter | EMA 200 |
| Stop / Target | 10% / 15% of ADR(20) |
| Session | RTH 09:30–16:00 ET |

## Files

```
server.js              Node static server + market-data proxy (DataSource seam)
public/index.html      The panel UI
public/indicators.js   Pure indicator math (SMA/EMA/RSI/MACD/ADX/BB) — Pine-matched
public/signal.js       v5 signal logic + ADR + RTH session + entry/stop/target
public/app.js          Fetch loop (30s) + render
```

## Next step (when you fund a TopStep account)

1. Generate a ProjectX API key.
2. Implement `getBars()` in a `ProjectXDataSource` (key → JWT → `/history`).
3. Set `ACTIVE_SOURCE` to it. Live (non-delayed) data, same panel.
4. Repackage `indicators.js` + `signal.js` + `index.html` as an MV3 extension
   content script to overlay the panel directly on TopstepX.
