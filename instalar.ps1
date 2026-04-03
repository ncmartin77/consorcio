# ============================================================
#  instalar.ps1  —  Instalador completamente automatico
#  App Consorcio
# ============================================================
#  Estrategia:
#    1. Usa Python de Windows si ya esta instalado (>= 3.8)
#    2. Si no, descarga e instala Python 3.12 en silencio
#    3. Si falla la descarga, instala WSL + Debian como fallback
#       (puede requerir reinicio; el script se reprograma solo)
#  En todos los casos: cero intervencion del usuario.
# ============================================================

param(
    [switch]$PostReboot   # pasado automaticamente tras reinicio
)

Set-StrictMode -Off
$ErrorActionPreference = "SilentlyContinue"

# ---- Paths ----
$AppDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogFile = Join-Path $AppDir "instalacion.log"
$Flag    = Join-Path $AppDir ".runtime"          # guarda "windows" o "wsl"

# ---- Logger ----
function Log {
    param([string]$Msg, [string]$Level = "INFO")
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [$Level] $Msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

# ---- Verificar admin ----
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")

if (-not $isAdmin) {
    Log "Relanzando con permisos de administrador..."
    $psArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`""
    if ($PostReboot) { $psArgs += " -PostReboot" }
    Start-Process powershell -Verb RunAs -ArgumentList $psArgs
    exit
}

Log "========================================================"
Log "  Instalador App Consorcio — inicio"
Log "  Directorio: $AppDir"
if ($PostReboot) { Log "  (continuacion post-reinicio)" }
Log "========================================================"

# ================================================================
#  FUNCION: buscar Python 3.8+ en Windows
# ================================================================
function Find-Python {
    $candidates = @("python", "py", "python3",
                    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
                    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
                    "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
                    "C:\Python312\python.exe", "C:\Python311\python.exe")

    foreach ($cmd in $candidates) {
        try {
            $ver = & $cmd --version 2>&1
            if ($ver -match "Python (\d+)\.(\d+)") {
                $maj = [int]$Matches[1]; $min = [int]$Matches[2]
                if ($maj -gt 3 -or ($maj -eq 3 -and $min -ge 8)) {
                    Log "Python $maj.$min encontrado: $cmd"
                    return $cmd
                }
            }
        } catch {}
    }
    return $null
}

# ================================================================
#  FUNCION: instalar Python 3.12 en silencio
# ================================================================
function Install-PythonWindows {
    $url     = "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"
    $tmpFile = Join-Path $env:TEMP "python_installer.exe"

    Log "Descargando Python 3.12 desde $url ..."
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $wc = New-Object System.Net.WebClient
        $wc.DownloadFile($url, $tmpFile)
    } catch {
        Log "Fallo la descarga: $_" "ERROR"
        return $false
    }

    if (-not (Test-Path $tmpFile) -or (Get-Item $tmpFile).Length -lt 1MB) {
        Log "Archivo descargado invalido o incompleto." "ERROR"
        return $false
    }

    Log "Instalando Python 3.12 (silencioso)..."
    $proc = Start-Process -FilePath $tmpFile -Wait -PassThru -ArgumentList `
        "/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1 Include_launcher=1 Include_doc=0"

    Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue

    if ($proc.ExitCode -ne 0) {
        Log "El instalador de Python termino con codigo $($proc.ExitCode)." "ERROR"
        return $false
    }

    # Refrescar PATH de la sesion actual
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path","User")

    Log "Python 3.12 instalado correctamente."
    return $true
}

# ================================================================
#  FUNCION: instalar WSL + Debian
# ================================================================
function Install-WSLDebian {
    Log "Verificando WSL..."

    # Comprobar si WSL ya tiene Debian
    $distros = wsl --list --quiet 2>$null
    if ($distros -match "Debian") {
        Log "Debian ya esta instalada en WSL."
        return "ready"
    }

    Log "Instalando WSL con Debian (sin intervencion)..."

    # Habilitar caracteristicas de Windows necesarias
    $feat1 = Get-WindowsOptionalFeature -Online -FeatureName "Microsoft-Windows-Subsystem-Linux" -ErrorAction SilentlyContinue
    $feat2 = Get-WindowsOptionalFeature -Online -FeatureName "VirtualMachinePlatform" -ErrorAction SilentlyContinue

    $needReboot = $false

    if ($feat1 -and $feat1.State -ne "Enabled") {
        Log "Habilitando Microsoft-Windows-Subsystem-Linux..."
        $r = Enable-WindowsOptionalFeature -Online -FeatureName "Microsoft-Windows-Subsystem-Linux" -NoRestart -All
        if ($r.RestartNeeded) { $needReboot = $true }
    }
    if ($feat2 -and $feat2.State -ne "Enabled") {
        Log "Habilitando VirtualMachinePlatform..."
        $r = Enable-WindowsOptionalFeature -Online -FeatureName "VirtualMachinePlatform" -NoRestart -All
        if ($r.RestartNeeded) { $needReboot = $true }
    }

    if ($needReboot) {
        Log "Se necesita reiniciar para completar WSL. Programando continuacion automatica..." "WARN"
        Schedule-ContinueAfterReboot
        Log "Reiniciando en 10 segundos..."
        Start-Sleep -Seconds 10
        Restart-Computer -Force
        exit
    }

    # Instalar distribucion Debian
    Log "Instalando distribucion Debian..."
    $proc = Start-Process -FilePath "wsl" -Wait -PassThru -ArgumentList "--install -d Debian --no-launch"
    if ($proc.ExitCode -ne 0) {
        # Metodo alternativo via wsl --install si el anterior falla
        wsl --install -d Debian --no-launch 2>&1 | ForEach-Object { Log $_ }
    }

    # Actualizar kernel de WSL2
    $kernelUrl = "https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi"
    $kernelFile = Join-Path $env:TEMP "wsl_update.msi"
    try {
        $wc = New-Object System.Net.WebClient
        $wc.DownloadFile($kernelUrl, $kernelFile)
        Start-Process msiexec -Wait -ArgumentList "/i `"$kernelFile`" /quiet /norestart"
        Remove-Item $kernelFile -Force -ErrorAction SilentlyContinue
        Log "Kernel WSL2 actualizado."
    } catch {
        Log "No se pudo actualizar el kernel WSL2 (puede que ya este actualizado): $_" "WARN"
    }

    wsl --set-default-version 2 2>&1 | Out-Null

    # Verificar si Debian quedo disponible
    Start-Sleep -Seconds 5
    $distros2 = wsl --list --quiet 2>$null
    if ($distros2 -match "Debian") {
        Log "Debian instalada en WSL correctamente."
        return "ready"
    }

    # Si el proceso necesita reinicio para terminar
    Log "WSL instalado. Puede ser necesario un reinicio." "WARN"
    Schedule-ContinueAfterReboot
    Log "Reiniciando en 10 segundos para terminar la instalacion de WSL..."
    Start-Sleep -Seconds 10
    Restart-Computer -Force
    exit
}

# ================================================================
#  FUNCION: programar continuacion tras reinicio
# ================================================================
function Schedule-ContinueAfterReboot {
    $psCmd  = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$AppDir\instalar.ps1`" -PostReboot"
    $regKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"
    Set-ItemProperty -Path $regKey -Name "ConsorcioInstalar" -Value $psCmd -Force
    Log "Continuacion programada en RunOnce."
}

# ================================================================
#  FUNCION: configurar Python en WSL Debian
# ================================================================
function Setup-WSL {
    Log "Configurando Python en WSL Debian..."

    # Convertir ruta Windows a ruta WSL (/mnt/c/...)
    $wslPath = $AppDir -replace "\\","/" -replace "^([A-Za-z]):","/mnt/`$1" `
                       -replace "^/mnt/([A-Za-z])", { "/mnt/$($_.Groups[1].Value.ToLower())" }
    # Forma mas segura: usar wslpath
    $wslPath = (wsl -d Debian -- wslpath -a $AppDir.Replace("\","/").Replace("C:","C:")) 2>$null
    if (-not $wslPath) {
        # Fallback manual
        $drive = $AppDir.Substring(0,1).ToLower()
        $rest  = $AppDir.Substring(2).Replace("\","/")
        $wslPath = "/mnt/$drive$rest"
    }
    $wslPath = $wslPath.Trim()
    Log "Ruta WSL del proyecto: $wslPath"

    $setupScript = @"
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv 2>&1
cd '$wslPath'
python3 -m venv venv_wsl
venv_wsl/bin/pip install --upgrade pip --quiet
venv_wsl/bin/pip install -r requirements.txt --quiet
mkdir -p data
echo "wsl_ok" > .wsl_setup_done
"@

    $tmpSh = Join-Path $env:TEMP "consorcio_setup.sh"
    [System.IO.File]::WriteAllText($tmpSh, $setupScript, [System.Text.Encoding]::UTF8)
    $tmpShWsl = (wsl -d Debian -- wslpath ($tmpSh.Replace("\","/"))) 2>$null
    if (-not $tmpShWsl) {
        $d2 = $tmpSh.Substring(0,1).ToLower()
        $r2 = $tmpSh.Substring(2).Replace("\","/")
        $tmpShWsl = "/mnt/$d2$r2"
    }
    $tmpShWsl = $tmpShWsl.Trim()

    Log "Ejecutando setup en Debian..."
    wsl -d Debian -- bash $tmpShWsl 2>&1 | ForEach-Object { Log "  [WSL] $_" }
    Remove-Item $tmpSh -Force -ErrorAction SilentlyContinue

    # Guardar ruta WSL para el launcher
    [System.IO.File]::WriteAllText($Flag, "wsl`n$wslPath", [System.Text.Encoding]::UTF8)
    Log "Entorno WSL configurado."
}

# ================================================================
#  FUNCION: configurar venv en Windows
# ================================================================
function Setup-Windows {
    param([string]$PythonCmd)

    $venvDir = Join-Path $AppDir "venv"

    if (-not (Test-Path (Join-Path $venvDir "Scripts\activate.bat"))) {
        Log "Creando entorno virtual..."
        & $PythonCmd -m venv $venvDir
        if ($LASTEXITCODE -ne 0) {
            Log "Error al crear el entorno virtual." "ERROR"
            return $false
        }
    } else {
        Log "Entorno virtual ya existe."
    }

    $pip = Join-Path $venvDir "Scripts\pip.exe"
    Log "Actualizando pip..."
    & $pip install --upgrade pip --quiet

    Log "Instalando dependencias..."
    & $pip install -r (Join-Path $AppDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        Log "Error al instalar dependencias." "ERROR"
        return $false
    }

    $dataDir = Join-Path $AppDir "data"
    if (-not (Test-Path $dataDir)) {
        New-Item -ItemType Directory -Path $dataDir | Out-Null
        Log "Carpeta data creada."
    }

    [System.IO.File]::WriteAllText($Flag, "windows", [System.Text.Encoding]::UTF8)
    return $true
}

# ================================================================
#  FUNCION: crear iniciar.bat adaptado al runtime elegido
# ================================================================
function Write-Launcher {
    param([string]$Runtime, [string]$WslPath = "")

    $launcherPath = Join-Path $AppDir "iniciar.bat"

    if ($Runtime -eq "windows") {
        $content = @"
@echo off
if not exist "%~dp0venv\Scripts\activate.bat" (
    echo El entorno virtual no existe. Ejecuta instalar.bat primero.
    pause
    exit /b 1
)
call "%~dp0venv\Scripts\activate.bat"
echo Iniciando App Consorcio en http://localhost:5000
start "" "http://localhost:5000"
python "%~dp0app.py"
"@
    } else {
        # WSL runtime
        $content = @"
@echo off
echo Iniciando App Consorcio en http://localhost:5000 (via WSL Debian)...
start "" "http://localhost:5000"
wsl -d Debian -- bash -c "cd '$WslPath' && source venv_wsl/bin/activate && python3 app.py"
"@
    }

    [System.IO.File]::WriteAllText($launcherPath, $content, [System.Text.Encoding]::ASCII)
    Log "Launcher actualizado: iniciar.bat (runtime=$Runtime)"
}

# ================================================================
#  FLUJO PRINCIPAL
# ================================================================

# Si es post-reinicio, esperar a que WSL termine de inicializarse
if ($PostReboot) {
    Log "Esperando inicializacion de WSL post-reinicio (30s)..."
    Start-Sleep -Seconds 30
}

$python = Find-Python

# ---- Camino 1: Python de Windows disponible ----
if ($python) {
    Log "--- Usando Python de Windows ---"
    $ok = Setup-Windows -PythonCmd $python
    if ($ok) {
        Write-Launcher -Runtime "windows"
        Log "========================================================"
        Log "  INSTALACION COMPLETADA — runtime: Windows Python"
        Log "  Ejecuta iniciar.bat para iniciar la app."
        Log "========================================================"
        exit 0
    }
    Log "Fallo la configuracion con Python de Windows. Intentando instalar Python..." "WARN"
}

# ---- Camino 2: Instalar Python de Windows silenciosamente ----
if (-not $python) {
    Log "--- Instalando Python para Windows ---"
    $installed = Install-PythonWindows

    if ($installed) {
        $python = Find-Python
        if ($python) {
            $ok = Setup-Windows -PythonCmd $python
            if ($ok) {
                Write-Launcher -Runtime "windows"
                Log "========================================================"
                Log "  INSTALACION COMPLETADA — runtime: Windows Python"
                Log "  Ejecuta iniciar.bat para iniciar la app."
                Log "========================================================"
                exit 0
            }
        }
    }
    Log "No se pudo instalar Python para Windows. Usando WSL Debian como fallback..." "WARN"
}

# ---- Camino 3: WSL Debian ----
Log "--- Instalando/configurando WSL Debian ---"
$wslResult = Install-WSLDebian   # puede reiniciar el equipo y no llegar aqui

if ($wslResult -eq "ready") {
    Setup-WSL

    # Leer wslPath del flag
    $flagContent = Get-Content $Flag -ErrorAction SilentlyContinue
    $wslPath = if ($flagContent -and $flagContent.Count -gt 1) { $flagContent[1] } else { "" }

    Write-Launcher -Runtime "wsl" -WslPath $wslPath

    Log "========================================================"
    Log "  INSTALACION COMPLETADA — runtime: WSL Debian"
    Log "  Ejecuta iniciar.bat para iniciar la app."
    Log "========================================================"
}
