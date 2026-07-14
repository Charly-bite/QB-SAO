@echo off
:: ================================================
::  Switch QB-OMS-PROD service to QB-SAO PROD
::  Run this as ADMINISTRATOR
:: ================================================
echo ================================================
echo   Switching QB-OMS-PROD to QB-SAO PROD
echo   Run as Administrator!
echo ================================================
echo.

set "NSSM=C:\Users\QB_DESARROLLO\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
set "NEW_DIR=C:\Users\QB_DESARROLLO\Desktop\QB-SAO PROD"
set "NEW_PYTHON=%NEW_DIR%\.venv\Scripts\python.exe"

echo [1/5] Stopping service...
"%NSSM%" stop QB-OMS-PROD confirm
timeout /t 3 /nobreak >nul

echo [2/5] Updating Application path...
"%NSSM%" set QB-OMS-PROD Application "%NEW_PYTHON%"

echo [3/5] Updating working directory...
"%NSSM%" set QB-OMS-PROD AppDirectory "%NEW_DIR%"

echo [4/5] Updating log paths...
"%NSSM%" set QB-OMS-PROD AppStdout "%NEW_DIR%\logs\service_stdout.log"
"%NSSM%" set QB-OMS-PROD AppStderr "%NEW_DIR%\logs\service_stderr.log"

echo [5/5] Starting service...
"%NSSM%" start QB-OMS-PROD

echo.
echo ================================================
echo   Done! Service now running from QB-SAO PROD
echo   Check http://192.168.2.218:5009
echo ================================================
pause
