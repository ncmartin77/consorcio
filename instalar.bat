@echo off
echo ============================================
echo  Instalador - App Consorcio Brasil
echo ============================================
echo.

:: Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no esta instalado.
    echo.
    echo Por favor instala Python desde: https://www.python.org/downloads/
    echo IMPORTANTE: Durante la instalacion, tildar la opcion "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

echo Python encontrado:
python --version
echo.

:: Crear entorno virtual
echo Creando entorno virtual...
python -m venv venv
if errorlevel 1 (
    echo ERROR al crear el entorno virtual.
    pause
    exit /b 1
)

:: Instalar dependencias
echo.
echo Instalando dependencias...
venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR al instalar dependencias.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Instalacion completada exitosamente!
echo  Ahora podes ejecutar "iniciar.bat"
echo ============================================
pause
