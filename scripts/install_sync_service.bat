@echo off
REM Install and start Open-OMS Sync Windows service
cd /d "%~dp0\.."
if exist ".venv\Scripts\activate.bat" (
  call .venv\Scripts\activate.bat
)
echo Installing Open-OMS Sync service (requires pywin32)
python ".\scripts\openoms_sync_service.py" install
python ".\scripts\openoms_sync_service.py" start
echo Service installed and started.
