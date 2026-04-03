# ============================================================
#  instalar.ps1  -  Instalador completamente automatico
#  App Consorcio
# ============================================================
#  Estrategia:
#    1. Usa Python de Windows si ya esta instalado (>= 3.8)
#    2. Si no, descarga e instala Python 3.12 en silencio
#    3. Si falla la descarga, instala WSL + Debian como fallback
# ============================================================

param([switch]$PostReboot)

Set-StrictMode -Off
$ErrorActionPreference = "Continue"

$AppDir  = $PSScriptRoot
$LogFile = Join-Path $AppDir "instalacion.log"
$Flag    = Join-Path $AppDir ".runtime"

function Log {
    param([string]$Msg, [string]$Level = "INFO")
    $line = "[" + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + "] [" + $Level + "] " + $Msg
    Write-Host $line
    try { Add-Content -Path $LogFile -Value $line -Encoding UTF8 -ErrorAction Stop }
    catch { Write-Host "  (no se pudo escribir al log: " + $_ + ")" }
}

Log ("PS1 iniciado. Ruta: " + $AppDir)
Log ("Usuario: " + $env:USERNAME + "  PostReboot: " + $PostReboot)

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")

if (-not $isAdmin) {
    Log "No es admin. Relanzando elevado..."
    $scriptPath = $MyInvocation.MyCommand.Path
    $args2 = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $scriptPath)
    if ($PostReboot) { $args2 += "-PostReboot" }
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $args2
    exit 0
}

Log "===================================================="
Log "  Instalador App Consorcio - ejecutando como admin"
Log ("  Directorio: " + $AppDir)
if ($PostReboot) { Log "  (continuacion post-reinicio)" }
Log "===================================================="

# ================================================================
#  FUNCION: buscar Python 3.8+ en Windows
# ================================================================
function Find-Python {
    $candidates = @(
        "python", "py", "python3",
        ($env:LOCALAPPDATA + "\Programs\Python\Python312\python.exe"),
        ($env:LOCALAPPDATA + "\Programs\Python\Python311\python.exe"),
        ($env:LOCALAPPDATA + "\Programs\Python\Python310\python.exe"),
        ($env:LOCALAPPDATA + "\Programs\Python\Python39\python.exe"),
        "C:\Python312\python.exe",
        "C:\Python311\python.exe"
    )
    foreach ($cmd in $candidates) {
        try {
            $ver = & $cmd --version 2>&1
            if ($ver -match "Python (\d+)\.(\d+)") {
                $maj = [int]$Matches[1]
                $min = [int]$Matches[2]
                if ($maj -gt 3 -or ($maj -eq 3 -and $min -ge 8)) {
                    Log ("Python " + $maj + "." + $min + " encontrado: " + $cmd)
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
    Log "Descargando Python 3.12 desde python.org..."
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $wc = New-Object System.Net.WebClient
        $wc.DownloadFile($url, $tmpFile)
    } catch {
        Log ("Fallo la descarga: " + $_) "ERROR"
        return $false
    }
    if (-not (Test-Path $tmpFile) -or (Get-Item $tmpFile).Length -lt 1048576) {
        Log "Archivo descargado invalido o incompleto." "ERROR"
        return $false
    }
    $fileMB = [math]::Round((Get-Item $tmpFile).Length / 1048576, 1)
    Log ("Descarga completa - " + $fileMB + " MB. Instalando...")
    $proc = Start-Process -FilePath $tmpFile -Wait -PassThru -ArgumentList `
        "/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1 Include_launcher=1 Include_doc=0"
    Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
    if ($proc.ExitCode -ne 0) {
        Log ("El instalador de Python termino con codigo " + $proc.ExitCode) "ERROR"
        return $false
    }
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath    = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path    = $machinePath + ";" + $userPath
    Log "Python 3.12 instalado. PATH actualizado."
    return $true
}

# ================================================================
#  FUNCION: instalar WSL + Debian
# ================================================================
function Install-WSLDebian {
    Log "Verificando WSL..."
    try {
        $distros = wsl --list --quiet 2>&1
        if ($distros -match "Debian") {
            Log "Debian ya esta instalada en WSL."
            return "ready"
        }
    } catch {}
    Log "Instalando WSL con Debian..."
    $needReboot = $false
    $feat1 = Get-WindowsOptionalFeature -Online -FeatureName "Microsoft-Windows-Subsystem-Linux" -ErrorAction SilentlyContinue
    $feat2 = Get-WindowsOptionalFeature -Online -FeatureName "VirtualMachinePlatform" -ErrorAction SilentlyContinue
    if ($feat1 -and $feat1.State -ne "Enabled") {
        Log "Habilitando Microsoft-Windows-Subsystem-Linux..."
        $r = Enable-WindowsOptionalFeature -Online -FeatureName "Microsoft-Windows-Subsystem-Linux" -NoRestart -All -ErrorAction SilentlyContinue
        if ($r -and $r.RestartNeeded) { $needReboot = $true }
    }
    if ($feat2 -and $feat2.State -ne "Enabled") {
        Log "Habilitando VirtualMachinePlatform..."
        $r = Enable-WindowsOptionalFeature -Online -FeatureName "VirtualMachinePlatform" -NoRestart -All -ErrorAction SilentlyContinue
        if ($r -and $r.RestartNeeded) { $needReboot = $true }
    }
    if ($needReboot) {
        Log "Reinicio necesario para activar WSL. Programando continuacion..." "WARN"
        Schedule-ContinueAfterReboot
        Log "Reiniciando en 10 segundos..."
        Start-Sleep -Seconds 10
        Restart-Computer -Force
        exit 0
    }
    $kernelUrl  = "https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi"
    $kernelFile = Join-Path $env:TEMP "wsl_update.msi"
    try {
        $wc = New-Object System.Net.WebClient
        $wc.DownloadFile($kernelUrl, $kernelFile)
        Start-Process msiexec -Wait -ArgumentList ("/i `"" + $kernelFile + "`" /quiet /norestart")
        Remove-Item $kernelFile -Force -ErrorAction SilentlyContinue
        Log "Kernel WSL2 actualizado."
    } catch {
        Log ("No se pudo actualizar kernel WSL2: " + $_) "WARN"
    }
    wsl --set-default-version 2 2>&1 | Out-Null
    Log "Instalando distribucion Debian..."
    Start-Process -FilePath "wsl.exe" -Wait -PassThru -ArgumentList "--install -d Debian --no-launch" -ErrorAction SilentlyContinue | Out-Null
    Start-Sleep -Seconds 10
    $distros2 = wsl --list --quiet 2>&1
    if ($distros2 -match "Debian") {
        Log "Debian instalada en WSL correctamente."
        return "ready"
    }
    Log "WSL instalado pero requiere reinicio." "WARN"
    Schedule-ContinueAfterReboot
    Log "Reiniciando en 10 segundos..."
    Start-Sleep -Seconds 10
    Restart-Computer -Force
    exit 0
}

# ================================================================
#  FUNCION: programar continuacion tras reinicio (RunOnce)
# ================================================================
function Schedule-ContinueAfterReboot {
    $scriptPath = $MyInvocation.ScriptName
    $cmd = "powershell -NoProfile -ExecutionPolicy Bypass -File `"" + $scriptPath + "`" -PostReboot"
    Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce" -Name "ConsorcioInstalar" -Value $cmd -Force
    Log "Continuacion post-reinicio registrada en RunOnce."
}

# ================================================================
#  FUNCION: configurar Python en WSL Debian
# ================================================================
function Setup-WSL {
    Log "Configurando Python en WSL Debian..."
    $drive   = $AppDir.Substring(0, 1).ToLower()
    $rest    = $AppDir.Substring(2) -replace "\\\\", "/"
    $wslPath = "/mnt/" + $drive + $rest
    Log ("Ruta WSL: " + $wslPath)

    $bashLines = @(
        "#!/bin/bash",
        "set -e",
        "export DEBIAN_FRONTEND=noninteractive",
        "apt-get update -qq",
        "apt-get install -y -qq python3 python3-pip python3-venv",
        ("cd '" + $wslPath + "'"),
        "if [ ! -d venv_wsl ]; then python3 -m venv venv_wsl; fi",
        "venv_wsl/bin/pip install --upgrade pip --quiet",
        "venv_wsl/bin/pip install -r requirements.txt --quiet",
        "mkdir -p data",
        "echo wsl_setup_ok"
    )
    $setupScript = $bashLines -join "`n"
    $tmpSh    = Join-Path $env:TEMP "consorcio_setup.sh"
    [System.IO.File]::WriteAllText($tmpSh, $setupScript, [System.Text.Encoding]::UTF8)
    $drive2   = $tmpSh.Substring(0, 1).ToLower()
    $rest2    = $tmpSh.Substring(2) -replace "\\\\", "/"
    $tmpShWsl = "/mnt/" + $drive2 + $rest2

    Log "Ejecutando setup en Debian (puede tardar unos minutos)..."
    wsl -d Debian -- bash $tmpShWsl 2>&1 | ForEach-Object { Log ("  [WSL] " + $_) }
    Remove-Item $tmpSh -Force -ErrorAction SilentlyContinue
    [System.IO.File]::WriteAllText($Flag, ("wsl`r`n" + $wslPath), [System.Text.Encoding]::ASCII)
    Log "Entorno WSL configurado correctamente."
    return $wslPath
}

# ================================================================
#  FUNCION: configurar venv en Windows
# ================================================================
function Setup-Windows {
    param([string]$PythonCmd)
    $venvDir = Join-Path $AppDir "venv"
    if (Test-Path (Join-Path $venvDir "Scripts\activate.bat")) {
        Log "Entorno virtual ya existe, verificando dependencias..."
    } else {
        Log ("Creando entorno virtual en " + $venvDir + " ...")
        & $PythonCmd -m venv $venvDir
        if ($LASTEXITCODE -ne 0) {
            Log ("Error al crear el entorno virtual (codigo " + $LASTEXITCODE + ")") "ERROR"
            return $false
        }
        Log "Entorno virtual creado."
    }
    $pip = Join-Path $venvDir "Scripts\pip.exe"
    Log "Actualizando pip..."
    & $pip install --upgrade pip --quiet
    Log "Instalando dependencias desde requirements.txt..."
    & $pip install -r (Join-Path $AppDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        Log ("Error al instalar dependencias (codigo " + $LASTEXITCODE + ")") "ERROR"
        return $false
    }
    $dataDir = Join-Path $AppDir "data"
    if (-not (Test-Path $dataDir)) {
        New-Item -ItemType Directory -Path $dataDir | Out-Null
        Log "Carpeta data/ creada."
    }
    [System.IO.File]::WriteAllText($Flag, "windows", [System.Text.Encoding]::ASCII)
    return $true
}

# ================================================================
#  FUNCION: crear iniciar.bat segun runtime
# ================================================================
function Write-Launcher {
    param([string]$Runtime, [string]$WslPath = "")
    $launcherPath = Join-Path $AppDir "iniciar.bat"
    if ($Runtime -eq "windows") {
        $lines = @(
            "@echo off",
            "if not exist `"%~dp0venv\Scripts\activate.bat`" (",
            "  echo Entorno no encontrado. Ejecuta instalar.bat primero.",
            "  pause",
            "  exit /b 1",
            ")",
            "call `"%~dp0venv\Scripts\activate.bat`"",
            "echo Iniciando App Consorcio en http://localhost:5000",
            "start `"`" `"http://localhost:5000`"",
            "python `"%~dp0app.py`""
        )
    } else {
        $bashCmd = "cd '" + $WslPath + "' && source venv_wsl/bin/activate && python3 app.py"
        $lines = @(
            "@echo off",
            "echo Iniciando App Consorcio via WSL Debian en http://localhost:5000...",
            "start `"`" `"http://localhost:5000`"",
            ("wsl -d Debian -- bash -c " + [char]34 + $bashCmd + [char]34)
        )
    }
    $content = $lines -join "`r`n"
    [System.IO.File]::WriteAllText($launcherPath, $content, [System.Text.Encoding]::ASCII)
    Log ("iniciar.bat generado (runtime=" + $Runtime + ")")
}

# ================================================================
#  FLUJO PRINCIPAL
# ================================================================

if ($PostReboot) {
    Log "Post-reinicio: esperando inicializacion de WSL (30s)..."
    Start-Sleep -Seconds 30
}

$python = Find-Python

if ($python) {
    Log "--- Camino 1: Python de Windows ---"
    $ok = Setup-Windows -PythonCmd $python
    if ($ok) {
        Write-Launcher -Runtime "windows"
        Log "===================================================="
        Log "  INSTALACION COMPLETADA  (runtime: Windows Python)"
        Log "  Ejecuta iniciar.bat para iniciar la app."
        Log "===================================================="
        Read-Host "`nInstalacion completa. Presiona Enter para cerrar"
        exit 0
    }
    Log "Fallo la configuracion con Python existente." "WARN"
}

Log "--- Camino 2: instalando Python 3.12 ---"
$installed = Install-PythonWindows

if ($installed) {
    $python = Find-Python
    if ($python) {
        $ok = Setup-Windows -PythonCmd $python
        if ($ok) {
            Write-Launcher -Runtime "windows"
            Log "===================================================="
            Log "  INSTALACION COMPLETADA  (runtime: Windows Python 3.12)"
            Log "  Ejecuta iniciar.bat para iniciar la app."
            Log "===================================================="
            Read-Host "`nInstalacion completa. Presiona Enter para cerrar"
            exit 0
        }
    }
}
Log "No se pudo instalar Python para Windows. Usando WSL Debian..." "WARN"

Log "--- Camino 3: WSL Debian ---"
$wslResult = Install-WSLDebian

if ($wslResult -eq "ready") {
    $wslPath = Setup-WSL
    Write-Launcher -Runtime "wsl" -WslPath $wslPath
    Log "===================================================="
    Log "  INSTALACION COMPLETADA  (runtime: WSL Debian)"
    Log "  Ejecuta iniciar.bat para iniciar la app."
    Log "===================================================="
    Read-Host "`nInstalacion completa. Presiona Enter para cerrar"
}