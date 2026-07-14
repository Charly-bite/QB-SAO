@echo off
echo ============================================
echo   Open-OMS — Pre-Commit Check
echo ============================================
cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

echo.
echo [1/2] Running tests...
%PYTHON% -m pytest tests/ -v --tb=short -q 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo ❌ PRE-COMMIT CHECK FAILED — Tests did not pass.
    echo    Fix the failing tests before committing.
    exit /b 1
)

echo.
echo [2/2] Checking for syntax errors...
%PYTHON% -m py_compile app.py 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ PRE-COMMIT CHECK FAILED — Syntax error in app.py
    exit /b 1
)

%PYTHON% -m py_compile config.py 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ PRE-COMMIT CHECK FAILED — Syntax error in config.py
    exit /b 1
)

echo.
echo ✅ PRE-COMMIT CHECK PASSED — Safe to commit.

