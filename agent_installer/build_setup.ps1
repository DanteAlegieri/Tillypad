#requires -Version 5.1
$ErrorActionPreference = "Stop"

# Нормальный вывод русского текста в Windows PowerShell.
try {
    chcp 65001 | Out-Null
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    Write-Warning "Не удалось переключить консоль на UTF-8."
}

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Get-PythonCommand {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return "py"
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return "python"
    }

    $python3 = Get-Command python3 -ErrorAction SilentlyContinue
    if ($python3) {
        return "python3"
    }

    throw @"
Python не найден.

Установите Python 3.11-3.13 x64 с python.org.
Во время установки включите:
  Add python.exe to PATH
  Install launcher for all users

После установки закройте PowerShell, откройте его заново
и повторно запустите build_setup.ps1.
"@
}

$PythonExe = Get-PythonCommand

Write-Host "Используется Python: $PythonExe" -ForegroundColor Green
& $PythonExe --version
if ($LASTEXITCODE -ne 0) {
    throw "Python найден, но не запускается."
}

Write-Host "Проверка pip..." -ForegroundColor Cyan
& $PythonExe -m pip --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "pip не найден. Выполняется ensurepip..." -ForegroundColor Yellow
    & $PythonExe -m ensurepip --upgrade
}

Write-Host "Установка инструментов сборки..." -ForegroundColor Cyan
& $PythonExe -m pip install --upgrade pip pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось установить PyInstaller."
}

Write-Host "Сборка AgentManager.exe..." -ForegroundColor Cyan
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
    throw "PyInstaller завершился с ошибкой."
}

$InnoCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)

$Inno = $InnoCandidates |
    Where-Object { $_ -and (Test-Path $_) } |
    Select-Object -First 1

if (-not $Inno) {
    throw @"
Inno Setup 6 не найден.

Установите Inno Setup 6, затем повторите сборку.
Ожидаемый файл:
  C:\Program Files (x86)\Inno Setup 6\ISCC.exe
или
  C:\Program Files\Inno Setup 6\ISCC.exe
"@
}

Write-Host "Используется Inno Setup: $Inno" -ForegroundColor Green
Write-Host "Сборка установщика..." -ForegroundColor Cyan

& $Inno "$PSScriptRoot\GastrodomRelayAgent.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup завершился с ошибкой."
}

$OutputFile = Join-Path `
    $PSScriptRoot `
    "output\RestaurantOS_RelayAgent_Setup_15_3.exe"

Write-Host ""
Write-Host "Установщик создан:" -ForegroundColor Green
Write-Host $OutputFile
