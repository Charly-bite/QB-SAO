@echo off
echo ========================================
echo   Open-OMS - Order Tracking
echo   Host: 192.168.2.134
echo   Port: 5009
echo ========================================
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe app.py
) else (
    python app.py
)
pause

