@echo off
title NQ Auto-Trader (Power-hour + ADX gate, 5 MNQ) -- ARMED on PRACTICE acct
cd /d "C:\Users\YOU\daytrading-automation\signal-tool"
set FEED=projectx
set ARMED=1
REM ---- Trade on the PRACTICE account (PRAC-V2-112211-37100419) until told otherwise. ----
REM Revert: delete the two lines below to fall back to the 50K Combine eval default (24717879).
set PROJECTX_ACCOUNT_ID=XXXX
set START_BALANCE=150000
if not exist logs mkdir logs
:loop
echo [%date% %time%] starting live-signal (ARMED) >> logs\bot-console.log
node live-signal.js >> logs\bot-console.log 2>&1
echo [%date% %time%] live-signal exited (code %errorlevel%). Restarting in 15s... >> logs\bot-console.log
timeout /t 15 /nobreak >nul
goto loop
