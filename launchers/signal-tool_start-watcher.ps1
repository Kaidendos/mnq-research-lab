# =============================================================
#  start-watcher.ps1 — keeps the NQ Discord watcher running.
#
#  Runs `node watcher.js` in a loop: if it ever exits/crashes it waits
#  10s and restarts, so the Discord alerts stay live. All output is
#  appended to watcher.log so you can see what it did while away.
#
#  Launched by:
#    - the Windows Scheduled Task "NQ-Discord-Watcher" (at logon), and/or
#    - double-clicking start-watcher.cmd, and/or
#    - manually:  powershell -ExecutionPolicy Bypass -File start-watcher.ps1
# =============================================================
$ErrorActionPreference = "Continue"
$here = "C:\Users\YOU\daytrading-automation\signal-tool"
Set-Location $here
$node = "C:\Program Files\nodejs\node.exe"
$log  = Join-Path $here "watcher.log"

"[$(Get-Date -Format o)] launcher started" | Out-File -FilePath $log -Append -Encoding utf8

while ($true) {
    "[$(Get-Date -Format o)] starting: node watcher.js" | Out-File -FilePath $log -Append -Encoding utf8
    & $node "watcher.js" *>> $log
    "[$(Get-Date -Format o)] watcher exited (code $LASTEXITCODE) - restarting in 10s" | Out-File -FilePath $log -Append -Encoding utf8
    Start-Sleep -Seconds 10
}
