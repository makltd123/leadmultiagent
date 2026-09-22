@echo off
set TASK_NAME=LeadMonitor
set PROJECT_DIR=%~dp0
set BAT_FILE=%PROJECT_DIR%autostart.bat

schtasks /create /tn "%TASK_NAME%" ^
  /tr "%BAT_FILE%" ^
  /sc onstart ^
  /ru SYSTEM ^
  /rl highest ^
  /f

echo Автозапуск зарегистрирован.
pause
