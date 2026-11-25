@echo off
title NQ Smoke Test (practice account, 1 MNQ round-trip)
cd /d "C:\Users\YOU\daytrading-automation\signal-tool"
set FEED=projectx
if not exist logs mkdir logs
echo [%date% %time%] starting smoke-test >> logs\smoke-test.log
node smoke-test.js >> logs\smoke-test.log 2>&1
echo [%date% %time%] smoke-test exited (code %errorlevel%) >> logs\smoke-test.log
