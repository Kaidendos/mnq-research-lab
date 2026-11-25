# ensure-fvg.ps1 — keep the FVG PAPER forward-test running (no orders).
# Launched by the FVG-Paper-EnsureRunning scheduled task at logon + every 15 min.
# If no node process is running live-fvg.js, (re)launch it hidden via the .vbs.
$r = Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object { $_.CommandLine -like '*live-fvg.js*' }
if (-not $r) {
  Start-Process -FilePath 'wscript.exe' `
    -ArgumentList '"C:\Users\YOU\daytrading-automation\signal-tool\run-fvg-hidden.vbs"' `
    -WorkingDirectory 'C:\Users\YOU\daytrading-automation\signal-tool'
}
