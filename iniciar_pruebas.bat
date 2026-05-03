@echo off
:: Inicia la app en MODO PRUEBAS.
:: Usa una base de datos separada (data\pruebas\edificio_brasil.xlsx)
:: y la carpeta ConsorcioApp/pruebas/ en Google Drive.
:: NO toca ni lee datos de producción.

set APPDIR=%~dp0
set APP_ENV=pruebas

:: Leer runtime del flag generado por el instalador
set RUNTIME=windows
if exist "%APPDIR%.runtime" (
    set /p RUNTIME=<"%APPDIR%.runtime"
)

echo.
echo  =====================================================
echo   App Consorcio - MODO PRUEBAS
echo   Base de datos: data\pruebas\edificio_brasil.xlsx
echo   Drive:         ConsorcioApp/pruebas/
echo   URL:           http://localhost:5000
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
start "" "http://localhost:5000"
python "%APPDIR%app.py"
goto :eof

:: ---- WSL Debian ----
:wsl_launch
for /f "usebackq skip=1 delims=" %%L in ("%APPDIR%.runtime") do (
    set WSLPATH=%%L
    goto :do_wsl
)
:do_wsl
start "" "http://localhost:5000"
wsl -d Debian -- bash -c "cd '%WSLPATH%' && source venv_wsl/bin/activate && APP_ENV=pruebas python3 app.py"
