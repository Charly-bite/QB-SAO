@echo off
echo ============================================
echo   Open-OMS — Dev Deployment
echo ============================================
cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
    set PIP=.venv\Scripts\pip.exe
) else (
    set PYTHON=python
    set PIP=pip
)

echo.
echo [1/4] Pulling latest from develop...
git pull origin develop
if %ERRORLEVEL% neq 0 (
    echo ⚠️ Git pull failed — continuing with local code
)

echo.
echo [2/4] Installing dependencies...
%PIP% install -r requirements.txt -q

echo.
echo [3/4] Running tests...
%PYTHON% -m pytest tests/ -v --tb=short -q
if %ERRORLEVEL% neq 0 (
    echo.
    echo ❌ DEPLOYMENT ABORTED — Tests failed.
    exit /b 1
)

echo.
echo [4/4] Starting dev server...
echo Press Ctrl+C to stop.
%PYTHON% app.py

