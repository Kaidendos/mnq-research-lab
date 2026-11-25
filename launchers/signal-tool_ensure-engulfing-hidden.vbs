' ensure-engulfing-hidden.vbs — run the keep-alive check with NO visible window.
' wscript has no console, and Run(..., 0, False) launches PowerShell hidden, so the
' Engulf-Heal scheduled task never flashes a command prompt.
CreateObject("WScript.Shell").Run "powershell.exe -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File ""C:\Users\YOU\daytrading-automation\signal-tool\ensure-engulfing.ps1""", 0, False
