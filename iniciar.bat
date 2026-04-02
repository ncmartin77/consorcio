@echo off
echo ============================================
echo  Iniciando App Consorcio Brasil...
echo ============================================
echo.

:: Verificar que existe el entorno virtual
if not exist "venv\Scripts\activate.bat" (
    echo El entorno virtual no existe. Ejecuta primero "instalar.bat"
    pause
    exit /b 1
)

:: Activar entorno virtual
call venv\Scripts\activate.bat

:: Iniciar la app
echo Abriendo el navegador en http://localhost:5000
echo Para cerrar la app, presiona Ctrl+C en esta ventana.
echo.
start "" "http://localhost:5000"
python app.py

pause
