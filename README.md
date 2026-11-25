# MNQ Research Lab

Backtesting lab for automated futures strategies on MNQ.
About 1,500 configs tested on 5 years of data, train/test split.
Only two edges survived out-of-sample. Most died.

See `results/` and `screenshots/`. Research code, not financial advice.

## Reproduce
`npm i`, set `DATABENTO_API_KEY`, run `node fetch-*.js`, then `node backtest.js`.
