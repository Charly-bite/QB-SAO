@echo off
echo ========================================
echo   Open-OMS - Order Tracking
echo   Port: 5003
echo ========================================
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe app.py
) else (
    python app.py
)
pause

