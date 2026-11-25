# ensure-engulfing.ps1 — keep the single ARMED Engulf@BB bot running.
# Launched by the Engulf-Heal scheduled task (every 15 min while logged on).
# If no node process is running live-engulfing.js, (re)launch it hidden via the .vbs.
# The bot's own .engulf-lock prevents duplicates, so a relaunch race is harmless.
$r = Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object { $_.CommandLine -like '*live-engulfing.js*' }
if (-not $r) {
  Start-Process -FilePath 'wscript.exe' `
    -ArgumentList '"C:\Users\YOU\daytrading-automation\signal-tool\run-engulfing-hidden.vbs"' `
    -WorkingDirectory 'C:\Users\YOU\daytrading-automation\signal-tool'
}
