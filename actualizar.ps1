# actualizar.ps1
# Pasos que ejecuta:
#   1. Backup automatico del Excel en la misma carpeta data/
#   2. Migra el esquema del Excel (agrega hojas/columnas nuevas)
#   3. Actualiza dependencias Python (por si hay nuevas)
# NO toca ni reemplaza data/edificio_brasil.xlsx con datos nuevos.

Set-StrictMode -Off
$ErrorActionPreference = "Continue"
$AppDir  = $PSScriptRoot
$LogFile = Join-Path $AppDir "actualizar.log"

function Log {
    param([string]$Msg, [string]$Level = "INFO")
    $line = "[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "] [" + $Level + "] " + $Msg
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
}

Log "===================================================="
Log "  Actualizacion App Consorcio"
Log ("  Directorio: " + $AppDir)
Log "===================================================="

# ---- 1. Backup del Excel ----
$dataDir = Join-Path $AppDir "data"
$xlsFile = Join-Path $dataDir "edificio_brasil.xlsx"

if (Test-Path $xlsFile) {
    $fecha      = Get-Date -Format "yyyyMMdd_HHmm"
    $backupName = "edificio_brasil_backup_" + $fecha + ".xlsx"
    $backupPath = Join-Path $dataDir $backupName
    Copy-Item -Path $xlsFile -Destination $backupPath -Force
    Log ("Backup creado: " + $backupName)
} else {
    Log "No existe base de datos aun. Se creara al iniciar la app." "WARN"
}

# ---- 2. Migracion de esquema ----
$python = $null
$venvPy = Join-Path $AppDir "venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $python = $venvPy
} else {
    foreach ($cmd in @("python", "py")) {
        try {
            $v = & $cmd --version 2>&1
            if ($v -match "Python 3") { $python = $cmd; break }
        } catch {}
    }
}

if ($python) {
    Log "Ejecutando migracion de esquema..."
    $output = & $python (Join-Path $AppDir "migrar.py") 2>&1
    $output | ForEach-Object { Log ("  " + $_) }
    Log "Migracion completada."
} else {
    Log "Python no encontrado. Ejecuta instalar.bat primero." "ERROR"
}

# ---- 3. Actualizar dependencias ----
$pip = Join-Path $AppDir "venv\Scripts\pip.exe"
if (Test-Path $pip) {
    Log "Actualizando dependencias..."
    & $pip install -r (Join-Path $AppDir "requirements.txt") --quiet
    Log "Dependencias actualizadas."
}

Log "===================================================="
Log "  ACTUALIZACION COMPLETADA"
Log "  Ejecuta iniciar.bat para iniciar la app."
Log "===================================================="
Write-Host ""
Read-Host "Actualizacion completa. Presiona Enter para cerrar"