@echo off
echo ===================================================
echo Iniciando Monitor SAO en modo Kiosco...
echo ===================================================
echo - El audio automatico esta forzado a encendido.
echo - La pantalla estara en pantalla completa.
echo.
echo Para salir del modo kiosco presione: ALT + F4
echo ===================================================
timeout /t 3

:: Si el Kiosco usa Google Chrome:
start chrome --kiosk "http://192.168.2.134:5009/orders/monitor" --autoplay-policy=no-user-gesture-required

:: Si el Kiosco usa Microsoft Edge (descomentar la linea de abajo y borrar la de Chrome):
:: start msedge --kiosk "http://192.168.2.134:5009/orders/monitor" --edge-kiosk-type=fullscreen --autoplay-policy=no-user-gesture-required
