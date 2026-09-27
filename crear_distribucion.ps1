# crear_distribucion.ps1
# Crea un ZIP listo para distribuir en otro equipo.
# Excluye: venv/, __pycache__/, .git/, el propio ZIP.
# Uso: click derecho → "Ejecutar con PowerShell"

$ErrorActionPreference = "Stop"

$src  = Split-Path -Parent $MyInvocation.MyCommand.Path
$date = Get-Date -Format "yyyyMMdd"
$dest = Join-Path $src "consorcio_app_$date.zip"

Write-Host "============================================"
Write-Host " Crear distribucion - App Consorcio"
Write-Host "============================================"
Write-Host ""
Write-Host "Carpeta origen : $src"
Write-Host "Archivo destino: $dest"
Write-Host ""

# Eliminar ZIP anterior si existe
if (Test-Path $dest) {
    Remove-Item $dest
    Write-Host "ZIP anterior eliminado."
}

# Recolectar archivos/carpetas a incluir
# Excluye: venv/, __pycache__/, .git/, data/ (el Excel de produccion
# nunca viaja en el ZIP — cada instalacion conserva su propia BD)
$excludeDirs = @("venv", "__pycache__", ".git", ".venv", "data")
$items = Get-ChildItem -Path $src | Where-Object {
    $_.Name -notin $excludeDirs -and
    $_.Extension -ne ".zip"
}

if (-not $items) {
    Write-Host "[ERROR] No se encontraron archivos para incluir." -ForegroundColor Red
    Read-Host "Presiona Enter para salir"
    exit 1
}

Write-Host "Archivos incluidos:"
$items | ForEach-Object { Write-Host "  + $($_.Name)" }
Write-Host ""

# Crear ZIP
Write-Host "Creando ZIP..."
Compress-Archive -Path $items.FullName -DestinationPath $dest -Force

$sizeMB = [math]::Round((Get-Item $dest).Length / 1MB, 2)
Write-Host ""
Write-Host "============================================"
Write-Host " ZIP creado exitosamente!" -ForegroundColor Green
Write-Host " Archivo: consorcio_app_$date.zip ($sizeMB MB)"
Write-Host ""
Write-Host " Instalacion nueva:"
Write-Host "  1. Copiar ZIP al otro equipo y descomprimir"
Write-Host "  2. Ejecutar instalar.bat"
Write-Host "  3. Ejecutar iniciar.bat"
Write-Host ""
Write-Host " Actualizacion (ya tiene datos cargados):"
Write-Host "  1. Hacer backup desde la app (boton Backup)"
Write-Host "  2. Descomprimir el ZIP encima de la carpeta actual"
Write-Host "  3. Ejecutar actualizar.bat (migra el esquema sin tocar datos)"
Write-Host "============================================"
Write-Host ""
Read-Host "Presiona Enter para salir"
