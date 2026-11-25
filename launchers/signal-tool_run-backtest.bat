@echo off
title NQ Backtest (live strategy)
cd /d "C:\Users\YOU\daytrading-automation\signal-tool"
echo Backtesting the LIVE strategy (power-hour + ADX^>20) on real history...
echo.
node backtest-live.js %1 %2
echo.
echo Done. Open the dashboard to see the results in the Backtest section.
pause
