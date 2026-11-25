@echo off
title Engulf@BB Paper Trade Monitor
color 0A
echo ============================================================
echo   ENGULF @ BB  —  Paper Trade Monitor
echo   Strategy: Engulfing Bar at Bollinger Band
echo   Time:     10:00am - 3:30pm ET only
echo   Stop:     1x ATR    Target: 3x ATR
echo   Risk:     $400/trade   Max: 3 trades/day
echo ============================================================
echo.
echo Signals will post to Discord automatically.
echo Enter trades MANUALLY on TopStep when you get an alert.
echo.
echo Starting monitor...
echo.
cd /d "%~dp0"
set PROJECTX_ACCOUNT_ID=XXXX
node live-engulfing.js
pause
