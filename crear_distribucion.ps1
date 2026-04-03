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

# Recolectar archivos/carpetas a incluir (excluir venv, __pycache__, .git, ZIPs)
$excludeDirs = @("venv", "__pycache__", ".git", ".venv")
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
Write-Host " Para instalar en otro equipo:"
Write-Host "  1. Copiar el ZIP al otro equipo"
Write-Host "  2. Descomprimir"
Write-Host "  3. Ejecutar instalar.bat"
Write-Host "  4. Ejecutar iniciar.bat"
Write-Host "============================================"
Write-Host ""
Read-Host "Presiona Enter para salir"
