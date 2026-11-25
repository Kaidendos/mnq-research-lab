@echo off
title FVG Paper Forward-Test (practice acct, PAPER -- NO ORDERS)
cd /d "C:\Users\YOU\daytrading-automation\signal-tool"
set FEED=projectx
set PROJECTX_ACCOUNT_ID=XXXX
if not exist logs mkdir logs
:loop
echo [%date% %time%] starting live-fvg (PAPER) >> logs\fvg-paper-console.log
node live-fvg.js >> logs\fvg-paper-console.log 2>&1
echo [%date% %time%] live-fvg exited (code %errorlevel%). Restarting in 15s... >> logs\fvg-paper-console.log
timeout /t 15 /nobreak >nul
goto loop
