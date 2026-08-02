#requires -Version 5.1
$ErrorActionPreference = "Stop"

try {
    chcp 65001 | Out-Null
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Get-PythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return "py"
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return "python"
    }
    if (Get-Command python3 -ErrorAction SilentlyContinue) {
        return "python3"
    }
    throw @"
Python не найден.

Установите Python 3.11-3.13 x64.
При установке включите:
  Add python.exe to PATH
  Install launcher for all users
"@
}

$PythonExe = Get-PythonCommand
Write-Host "Используется Python: $PythonExe" -ForegroundColor Green
& $PythonExe --version

Write-Host "Установка зависимостей..." -ForegroundColor Cyan
& $PythonExe -m pip install --upgrade pip pyinstaller
& $PythonExe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось установить зависимости."
}

Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue

Write-Host "1/3 Сборка AgentManager.exe..." -ForegroundColor Cyan
& $PythonExe -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name AgentManager `
  --hidden-import win32timezone `
  --hidden-import pyodbc `
  agent_manager.py
if ($LASTEXITCODE -ne 0) {
    throw "Ошибка сборки AgentManager.exe"
}

Write-Host "2/3 Сборка AgentService.exe..." -ForegroundColor Cyan
& $PythonExe -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --noconsole `
  --name AgentService `
  --hidden-import win32timezone `
  --hidden-import pyodbc `
  --hidden-import websockets `
  --hidden-import servicemanager `
  --hidden-import win32service `
  --hidden-import win32serviceutil `
  agent_service_host.py
if ($LASTEXITCODE -ne 0) {
    throw "Ошибка сборки AgentService.exe"
}

$Separator = ";"
if (-not $IsWindows) {
    $Separator = ":"
}

$ManagerData = "dist\AgentManager.exe${Separator}."
$ServiceData = "dist\AgentService.exe${Separator}."
$EnvData = "agent_installer\agent.env.example${Separator}."

Write-Host "3/3 Сборка SetupAgent.exe..." -ForegroundColor Cyan
& $PythonExe -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --uac-admin `
  --name RestaurantOS_Agent_Setup_15_4 `
  --add-data $ManagerData `
  --add-data $ServiceData `
  --add-data $EnvData `
  setup_agent.py
if ($LASTEXITCODE -ne 0) {
    throw "Ошибка сборки SetupAgent.exe"
}

$Output = Join-Path `
    $Root `
    "dist\RestaurantOS_Agent_Setup_15_4.exe"

Write-Host ""
Write-Host "Готово!" -ForegroundColor Green
Write-Host "Установщик:" -ForegroundColor Green
Write-Host $Output
Write-Host ""
Write-Host "Inno Setup больше не требуется." -ForegroundColor Yellow
