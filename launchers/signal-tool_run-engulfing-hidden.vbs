' Launch the single ARMED Engulf@BB auto-trade bot with NO visible window (style 0).
' start-engulfing-armed.bat sets ARMED=1 + PROJECTX_ACCOUNT_ID=XXXX (practice).
' The bot's own single-instance lock guarantees a second copy exits immediately.
CreateObject("WScript.Shell").Run "cmd /c ""C:\Users\YOU\daytrading-automation\signal-tool\start-engulfing-armed.bat""", 0, False
