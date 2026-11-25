@echo off
title Engulf@BB — Live Forward-Test Scorecard
color 0B
cd /d "%~dp0"
node live-report.js
echo.
echo (also saved to logs\forward-test-report.md)
echo.
pause
