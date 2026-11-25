@echo off
title NQ Auto-Trader Dashboard
cd /d "C:\Users\YOU\daytrading-automation\signal-tool"
echo Starting the NQ dashboard... your browser will open at http://localhost:8787
echo Close this window to stop the dashboard (the trading bot keeps running).
node dashboard.js
pause
