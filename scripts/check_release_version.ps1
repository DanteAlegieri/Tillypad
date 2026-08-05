$ErrorActionPreference = "Stop"

$Expected = "8.1.2"
$Files = @(
    ".\gateway\app\main.py",
    ".\gateway\app\owner_dashboard.py",
    ".\RELEASE_VERSION.txt",
    ".\deploy_vps.ps1"
)

foreach ($File in $Files) {
    if (-not (Test-Path $File)) {
        throw "Не найден файл: $File"
    }

    $Text = Get-Content $File -Raw
    if ($Text -notmatch [regex]::Escape($Expected)) {
        throw "Версия $Expected не найдена в $File"
    }
}

Write-Host "Версии согласованы: $Expected" -ForegroundColor Green
