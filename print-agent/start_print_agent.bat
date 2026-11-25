@echo off
REM Starts the Biashara360 print program. Keep this window open, or start it at boot with Task Scheduler.
cd /d "%~dp0"
:loop
py -3 print_agent.py
echo The print program stopped. Restarting in 10 seconds...
timeout /t 10 /nobreak >nul
goto loop
