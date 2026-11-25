' ensure-fvg-hidden.vbs — run the keep-alive check with NO visible window.
' wscript has no console, and Run(..., 0, False) launches PowerShell hidden, so
' the FVG-Paper-Heal scheduled task no longer flashes a command prompt every 15 min.
CreateObject("WScript.Shell").Run "powershell.exe -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File ""C:\Users\YOU\daytrading-automation\signal-tool\ensure-fvg.ps1""", 0, False
