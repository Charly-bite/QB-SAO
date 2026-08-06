@echo off
:: ================================================
::  Restart QB-OMS-PROD service (Run as Admin)
:: ================================================
echo Restarting QB-OMS-PROD service...

set "NSSM=C:\Users\QB_DESARROLLO\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"

"%NSSM%" restart QB-OMS-PROD confirm

echo.
echo Done. Service restarted with new permission system.
echo Check: http://192.168.2.218:5009/orders/facturas
pause
