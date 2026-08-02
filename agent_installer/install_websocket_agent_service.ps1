#requires -RunAsAdministrator
param(
    [string]$InstallDir = "$env:ProgramFiles\Gastrodom\RelayAgent",
    [string]$DataDir = "$env:ProgramData\Gastrodom\RelayAgent"
)

$ErrorActionPreference = "Stop"
$ServiceName = "GastrodomRelayAgent"
$PythonExe = Join-Path $InstallDir ".venv\Scripts\python.exe"
$ServiceScript = Join-Path $InstallDir "app\websocket_agent_windows_service.py"

if (-not (Test-Path $PythonExe)) {
    throw "Python окружение агента не найдено: $PythonExe"
}
if (-not (Test-Path $ServiceScript)) {
    throw "Файл службы не найден: $ServiceScript"
}

$env:GASTRODOM_ENV_FILE = Join-Path $DataDir "agent.env"

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    & $PythonExe $ServiceScript update --startup auto
} else {
    & $PythonExe $ServiceScript install --startup auto
}

sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
sc.exe failureflag $ServiceName 1 | Out-Null

Start-Service -Name $ServiceName
Write-Host "Служба $ServiceName установлена и запущена." -ForegroundColor Green
