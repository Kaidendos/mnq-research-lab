' Launch the NQ dry-run bot with NO visible window (style 0), so it runs
' silently in the background. Called by the Windows Task Scheduler at logon.
CreateObject("WScript.Shell").Run "cmd /c ""C:\Users\YOU\daytrading-automation\signal-tool\start-bot.bat""", 0, False
