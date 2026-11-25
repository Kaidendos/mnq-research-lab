# MNQ Research Lab

Backtesting and validation lab for automated futures strategies on MNQ.
Built to answer one question: does any of this survive out-of-sample?

~1,500 configurations across 5 years of minute data, train/test split,
Monte Carlo and payout-before-bust simulation under real prop-firm rules.

## What survived
EMA trend continuation and volatility breakout. Both modest, both regime-dependent.

## What died
FVG, KeyRev, engulfing, RSI2, most ICT concepts, calendar anomalies.
Ten configs were strong on test and failed train - data-mined, not found.

## Structure
- `scripts/` research, backtests, ranking sweeps, control tests
- `notes/` build log and forward-test reports
- `indicators/` Pine Script versions
- `launchers/` Windows task wrappers
- `outputs/` result CSVs
- `screenshots/` live dashboard

## Caveats
Slippage modelled loosely. One instrument. Not financial advice.
