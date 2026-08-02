#requires -RunAsAdministrator
param(
    [string]$InstallDir = "$env:ProgramFiles\Gastrodom\RelayAgent",
    [string]$DataDir = "$env:ProgramData\Gastrodom\RelayAgent",
    [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"
$ServiceName = "GastrodomRelayAgent"
$SourceRoot = Split-Path -Parent $PSScriptRoot

Write-Host "Установка Gastrodom Relay Agent..." -ForegroundColor Cyan

if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
    Write-Host "Останавливаю существующую службу..."
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
New-Item -ItemType Directory -Force -Path "$DataDir\logs" | Out-Null
New-Item -ItemType Directory -Force -Path "$DataDir\cache" | Out-Null

Write-Host "Копирую файлы в Program Files..."
robocopy $SourceRoot $InstallDir /MIR `
    /XD ".git" "__pycache__" ".relay_cache" "agent_installer" `
    /XF ".env" "*.pyc" | Out-Null

$VenvDir = Join-Path $InstallDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    Write-Host "Создаю изолированное Python-окружение..."
    & $PythonCommand -m venv $VenvDir
}

Write-Host "Устанавливаю зависимости..."
& $PythonExe -m pip install --disable-pip-version-check --upgrade pip
& $PythonExe -m pip install --disable-pip-version-check -r "$InstallDir\requirements.txt"
& $PythonExe -m pywin32_postinstall -install 2>$null

$EnvFile = Join-Path $DataDir "agent.env"
if (-not (Test-Path $EnvFile)) {
    Copy-Item "$PSScriptRoot\agent.env.example" $EnvFile
    Write-Warning "Создан шаблон $EnvFile. Заполните SQL-параметры и API-ключ."
}

# Папка ProgramData скрыта и доступна только администраторам и SYSTEM.
attrib +h $DataDir
icacls $DataDir /inheritance:r | Out-Null
icacls $DataDir /grant:r `
    "SYSTEM:(OI)(CI)F" `
    "Administrators:(OI)(CI)F" | Out-Null

# Program Files только для чтения обычным пользователям по стандартным правам Windows.
$ServiceScript = Join-Path $InstallDir "app\relay_windows_service.py"

if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
    & $PythonExe $ServiceScript update --startup auto
} else {
    & $PythonExe $ServiceScript install --startup auto
}

# Служба работает от LocalSystem. Доступ к SQL лучше давать отдельному SQL readonly-пользователю.
sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
sc.exe failureflag $ServiceName 1 | Out-Null

Start-Service -Name $ServiceName

Write-Host ""
Write-Host "Gastrodom Relay Agent установлен." -ForegroundColor Green
Write-Host "Служба: $ServiceName"
Write-Host "Программа: $InstallDir"
Write-Host "Настройки: $EnvFile"
Write-Host ""
Write-Host "После изменения agent.env перезапустите службу:" -ForegroundColor Yellow
Write-Host "Restart-Service $ServiceName"
