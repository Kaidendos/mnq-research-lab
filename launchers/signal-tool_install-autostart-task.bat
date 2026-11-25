@echo off
:: Run this once as Administrator to register the auto-start scheduled task.
:: Right-click -> Run as administrator

echo Installing EngulfBB-AutoTrade scheduled task...
echo.

powershell -Command ^
  "$action = New-ScheduledTaskAction -Execute 'C:\Users\YOU\daytrading-automation\signal-tool\start-engulfing-armed.bat';" ^
  "$t1 = New-ScheduledTaskTrigger -AtLogOn;" ^
  "$t2 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '9:25AM';" ^
  "$s  = New-ScheduledTaskSettingsSet -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Hours 8);" ^
  "Register-ScheduledTask -TaskName 'EngulfBB-AutoTrade' -Action $action -Trigger $t1,$t2 -Settings $s -RunLevel Highest -Force | Out-Null;" ^
  "Write-Host 'Task registered successfully.'"

echo.
echo Done. The bot will now:
echo   - Start automatically on every login
echo   - Start automatically at 9:25am ET on weekdays (wakes PC if asleep)
echo.
pause
