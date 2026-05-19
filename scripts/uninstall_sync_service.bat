@echo off
cd /d "%~dp0\.."
if exist ".venv\Scripts\activate.bat" (
  call .venv\Scripts\activate.bat
)
echo Stopping and uninstalling Open-OMS Sync service
python ".\scripts\openoms_sync_service.py" stop
python ".\scripts\openoms_sync_service.py" remove
echo Service removed.
