#requires -RunAsAdministrator
param(
    [string]$InstallDir = "$env:ProgramFiles\Gastrodom\RelayAgent",
    [string]$DataDir = "$env:ProgramData\Gastrodom\RelayAgent",
    [switch]$RemoveData
)

$ErrorActionPreference = "Stop"
$ServiceName = "GastrodomRelayAgent"

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($service) {
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue

    $PythonExe = Join-Path $InstallDir ".venv\Scripts\python.exe"
    $ServiceScript = Join-Path $InstallDir "app\relay_windows_service.py"

    if ((Test-Path $PythonExe) -and (Test-Path $ServiceScript)) {
        & $PythonExe $ServiceScript remove
    } else {
        sc.exe delete $ServiceName | Out-Null
    }
}

if (Test-Path $InstallDir) {
    Remove-Item -Recurse -Force $InstallDir
}

if ($RemoveData -and (Test-Path $DataDir)) {
    Remove-Item -Recurse -Force $DataDir
}

Write-Host "Gastrodom Relay Agent удалён." -ForegroundColor Green
if (-not $RemoveData) {
    Write-Host "Настройки и журналы сохранены: $DataDir"
}
