@echo off
title Lunch Paper-Trader (Keltner fade, DRY-RUN, NO ORDERS)
cd /d "C:\Users\YOU\daytrading-automation\signal-tool"
if not exist logs mkdir logs
:loop
echo [%date% %time%] starting lunch-paper (DRY-RUN) >> logs\lunch-console.log
node lunch-paper.js >> logs\lunch-console.log 2>&1
echo [%date% %time%] lunch-paper exited (code %errorlevel%). Restarting in 15s... >> logs\lunch-console.log
timeout /t 15 /nobreak >nul
goto loop
