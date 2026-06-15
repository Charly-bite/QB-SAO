@echo off
echo ============================================
echo   Open-OMS — Running Tests
echo ============================================
cd /d "%~dp0\.."

if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

echo Using: %PYTHON%
echo.

%PYTHON% -m pytest tests/ -v --tb=short --cov=. --cov-report=term-missing --cov-config=.coveragerc 2>&1

if %ERRORLEVEL% neq 0 (
    echo.
    echo ❌ TESTS FAILED
    exit /b 1
) else (
    echo.
    echo ✅ ALL TESTS PASSED
)

