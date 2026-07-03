@echo off
echo ========================================
echo   Open-OMS - Order Tracking
echo   Host: 192.168.2.134
echo   Port: 5009
echo ========================================
cd /d "%~dp0"

:: ── Cleanup: Kill any existing processes on port 5009 ──
echo.
echo [CLEANUP] Checking for existing processes on port 5009...
set "FOUND=0"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5009 " ^| findstr "LISTEN ESTABLISHED TIME_WAIT"') do (
    if %%p NEQ 0 (
        echo [CLEANUP] Killing PID %%p...
        taskkill /PID %%p /F >nul 2>&1
        set "FOUND=1"
    )
)
if "%FOUND%"=="1" (
    echo [CLEANUP] Old processes killed. Waiting 2s for port release...
    timeout /t 2 /nobreak >nul
) else (
    echo [CLEANUP] Port 5009 is clean.
)

:: ── Start the application ──
echo.
echo [START] Launching Open-OMS...
echo.
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe app.py
) else (
    python app.py
)

:: ── On exit: Clean up any leftover processes ──
echo.
echo [SHUTDOWN] Cleaning up processes on port 5009...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5009 " ^| findstr "LISTEN ESTABLISHED TIME_WAIT"') do (
    if %%p NEQ 0 (
        echo [SHUTDOWN] Killing PID %%p...
        taskkill /PID %%p /F >nul 2>&1
    )
)
echo [SHUTDOWN] Cleanup complete.
pause
