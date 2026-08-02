#requires -RunAsAdministrator
param(
    [string]$DataDir = "$env:ProgramData\Gastrodom\RelayAgent"
)

$ErrorActionPreference = "Stop"
$EnvFile = Join-Path $DataDir "agent.env"

if (-not (Test-Path $EnvFile)) {
    throw "Файл конфигурации не найден: $EnvFile"
}

notepad.exe $EnvFile
Write-Host ""
Write-Host "После сохранения перезапустите службу:" -ForegroundColor Yellow
Write-Host "Restart-Service GastrodomRelayAgent"
