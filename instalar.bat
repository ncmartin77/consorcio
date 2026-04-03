@echo off
setlocal EnableDelayedExpansion
echo ============================================
echo  Instalador - App Consorcio
echo ============================================
echo.

:: ---- 1. Verificar Python 3.8+ ----
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta instalado o no esta en el PATH.
    echo.
    echo  Descargalo desde: https://www.python.org/downloads/
    echo  IMPORTANTE: Durante la instalacion tildar "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

:: Verificar version minima 3.8
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do (
    set PYMAJ=%%a
    set PYMIN=%%b
)
if !PYMAJ! LSS 3 (
    echo [ERROR] Se requiere Python 3.8 o superior. Version encontrada: !PYVER!
    pause
    exit /b 1
)
if !PYMAJ! EQU 3 if !PYMIN! LSS 8 (
    echo [ERROR] Se requiere Python 3.8 o superior. Version encontrada: !PYVER!
    pause
    exit /b 1
)
echo [OK] Python !PYVER! encontrado.

:: ---- 2. Verificar pip ----
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pip no encontrado. Reinstala Python desde python.org
    pause
    exit /b 1
)
echo [OK] pip disponible.

:: ---- 3. Verificar requirements.txt ----
if not exist "requirements.txt" (
    echo [ERROR] No se encontro requirements.txt en esta carpeta.
    echo  Asegurate de ejecutar este archivo desde la carpeta del proyecto.
    pause
    exit /b 1
)

:: ---- 4. Crear entorno virtual ----
if exist "venv\Scripts\activate.bat" (
    echo [OK] Entorno virtual ya existe, omitiendo creacion.
) else (
    echo Creando entorno virtual...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
    echo [OK] Entorno virtual creado.
)

:: ---- 5. Instalar/actualizar dependencias ----
echo.
echo Instalando dependencias (Flask, openpyxl, reportlab)...
venv\Scripts\pip install --upgrade pip >nul 2>&1
venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias.
    echo  Revisa tu conexion a internet e intentalo nuevamente.
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas.

:: ---- 6. Verificar carpeta data ----
if not exist "data" (
    echo Creando carpeta data...
    mkdir data
)

:: ---- 7. Verificar que el archivo Excel exista ----
if not exist "data\edificio_brasil.xlsx" (
    echo.
    echo [AVISO] No se encontro data\edificio_brasil.xlsx
    echo  La app lo creara automaticamente al iniciar por primera vez.
)

echo.
echo ============================================
echo  Instalacion completada exitosamente!
echo.
echo  Para iniciar la app ejecuta: iniciar.bat
echo ============================================
echo.
pause
