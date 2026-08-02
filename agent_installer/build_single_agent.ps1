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
В установщике отметьте:
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

Write-Host "Сборка единого RestaurantOSAgent.exe..." -ForegroundColor Cyan

& $PythonExe -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --uac-admin `
  --name RestaurantOSAgent_17_0_0 `
  --hidden-import win32timezone `
  --hidden-import pyodbc `
  --hidden-import websockets `
  --hidden-import servicemanager `
  --hidden-import win32service `
  --hidden-import win32serviceutil `
  --hidden-import app.websocket_agent_client `
  --hidden-import app.agent_diagnostics `
  --hidden-import app.service_manager `
  --hidden-import app.sql_autodetect `
  --hidden-import app.payload_codec `
  --hidden-import app.query_cache `
  --hidden-import http.server `
  --hidden-import app.local_agent_web `
  --hidden-import app.agent_state `
  restaurant_os_agent.py

if ($LASTEXITCODE -ne 0) {
    throw "Ошибка сборки RestaurantOSAgent.exe."
}

$Output = Join-Path $Root "dist\RestaurantOSAgent_17_0_0.exe"

Write-Host ""
Write-Host "Готово!" -ForegroundColor Green
Write-Host "Единственный файл для передачи клиенту:" -ForegroundColor Green
Write-Host $Output
Write-Host ""
Write-Host "Режимы одного файла:" -ForegroundColor Yellow
Write-Host "  RestaurantOSAgent.exe             установка"
Write-Host "  RestaurantOSAgent.exe --config    настройки"
Write-Host "  RestaurantOSAgent.exe --run-service служба"
