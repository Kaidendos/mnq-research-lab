@echo off
REM Double-click to start the NQ Discord watcher in this window.
REM Close the window (or Ctrl+C) to stop it. Logs go to watcher.log.
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0start-watcher.ps1"
