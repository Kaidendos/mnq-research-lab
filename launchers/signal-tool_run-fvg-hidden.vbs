' Launch the FVG paper forward-test with NO visible window (style 0), so it runs
' silently in the background. Paper only — places no orders. Add to Task Scheduler
' at logon for auto-start, or run this .vbs manually.
CreateObject("WScript.Shell").Run "cmd /c ""C:\Users\YOU\daytrading-automation\signal-tool\start-fvg-paper.bat""", 0, False
