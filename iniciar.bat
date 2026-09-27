@echo off
:: Launcher inteligente: detecta el runtime instalado (.runtime)
:: y usa Windows Python o WSL Debian segun corresponda.

set APPDIR=%~dp0

:: Leer runtime del flag generado por el instalador
set RUNTIME=windows
if exist "%APPDIR%.runtime" (
    set /p RUNTIME=<"%APPDIR%.runtime"
)

if /i "%RUNTIME%"=="wsl" goto :wsl_launch

:: ---- Windows Python ----
if not exist "%APPDIR%venv\Scripts\activate.bat" (
    echo [ERROR] El entorno virtual no existe.
    echo.
    if exist "%APPDIR%instalacion.log" (
        echo La instalacion tuvo errores. Revisa el log:
        echo %APPDIR%instalacion.log
    ) else (
        echo Ejecuta instalar.bat primero.
    )
    echo.
    pause
    exit /b 1
)
echo Iniciando App Consorcio en http://localhost:5000
call "%APPDIR%venv\Scripts\activate.bat"
start "" "http://localhost:5000"
python "%APPDIR%app.py"
goto :eof

:: ---- WSL Debian ----
:wsl_launch
echo Iniciando App Consorcio en http://localhost:5000 (via WSL Debian)...
for /f "usebackq skip=1 delims=" %%L in ("%APPDIR%.runtime") do (
    set WSLPATH=%%L
    goto :do_wsl
)
:do_wsl
start "" "http://localhost:5000"
wsl -d Debian -- bash -c "cd '%WSLPATH%' && source venv_wsl/bin/activate && python3 app.py"
