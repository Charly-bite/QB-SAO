@echo off
REM Start the Open-OMS sync daemon using the repository virtualenv
cd /d "%~dp0\.."
if exist ".venv\Scripts\activate.bat" (
  call .venv\Scripts\activate.bat
)
.
".venv\Scripts\python.exe" ".\scripts\sync_print_daemon.py" %*
