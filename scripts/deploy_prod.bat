@echo off
echo ============================================
echo   Open-OMS — Production Deployment
echo ============================================
echo.
cd /d "%~dp0\.."

REM Determine Python executable
if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
    set PIP=.venv\Scripts\pip.exe
) else (
    set PYTHON=python
    set PIP=pip
)

echo [1/5] Pulling latest from main...
git pull origin main
if %ERRORLEVEL% neq 0 (
    echo.
    echo   ERROR: Git pull failed. Resolve conflicts before deploying.
    exit /b 1
)

echo.
echo [2/5] Installing / updating dependencies...
%PIP% install -r requirements.txt -q
if %ERRORLEVEL% neq 0 (
    echo.
    echo   WARNING: Some dependencies may have failed to install.
    echo   Check the output above for errors.
)

echo.
echo [3/5] Running smoke tests...
set FLASK_ENV=testing
%PYTHON% -m pytest tests/ -v --tb=short -q
if %ERRORLEVEL% neq 0 (
    echo.
    echo   ==========================================
    echo   DEPLOYMENT ABORTED — Tests failed.
    echo   Fix the failing tests before deploying.
    echo   ==========================================
    exit /b 1
)

echo.
echo [4/5] Creating logs directory...
if not exist "logs" mkdir logs

echo.
echo [5/5] Starting production server...
echo   Environment: production
echo   Port: 5003
echo   Press Ctrl+C to stop.
echo.
set FLASK_ENV=production
%PYTHON% app.py
