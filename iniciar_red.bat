@echo off
:: Inicia la app escuchando en todas las interfaces (accesible desde la red local).
:: Detecta automaticamente la IP local para abrir el navegador en la direccion correcta.

set APPDIR=%~dp0

:: Leer runtime del flag generado por el instalador
set RUNTIME=windows
if exist "%APPDIR%.runtime" (
    set /p RUNTIME=<"%APPDIR%.runtime"
)

:: Detectar IP local (primera IPv4 que no sea 127.x)
for /f %%i in ('powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown'} | Sort-Object -Property InterfaceIndex | Select-Object -First 1).IPAddress"') do set LOCAL_IP=%%i

if "%LOCAL_IP%"=="" (
    echo [AVISO] No se pudo detectar la IP local. Usando 0.0.0.0
    set LOCAL_IP=0.0.0.0
)

echo.
echo  =====================================================
echo   App Consorcio - Modo RED LOCAL
echo   Acceso desde esta PC:  http://localhost:5000
echo   Acceso desde la red:   http://%LOCAL_IP%:5000
echo  =====================================================
echo.

if /i "%RUNTIME%"=="wsl" goto :wsl_launch

:: ---- Windows Python ----
if not exist "%APPDIR%venv\Scripts\activate.bat" (
    echo [ERROR] El entorno virtual no existe. Ejecuta instalar.bat primero.
    pause
    exit /b 1
)
call "%APPDIR%venv\Scripts\activate.bat"
set APP_HOST=0.0.0.0
start "" "http://%LOCAL_IP%:5000"
python "%APPDIR%app.py"
goto :eof

:: ---- WSL Debian ----
:wsl_launch
for /f "usebackq skip=1 delims=" %%L in ("%APPDIR%.runtime") do (
    set WSLPATH=%%L
    goto :do_wsl
)
:do_wsl
start "" "http://%LOCAL_IP%:5000"
wsl -d Debian -- bash -c "cd '%WSLPATH%' && source venv_wsl/bin/activate && APP_HOST=0.0.0.0 python3 app.py"
