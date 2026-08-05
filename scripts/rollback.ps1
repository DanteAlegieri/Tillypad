[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [string]$VpsHost = "5.8.53.75",

    [string]$VpsUser = "root"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$tag = "v$Version"

git rev-parse --verify $tag *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Тег $tag не найден."
}

$temporaryBranch = "rollback/$Version-$(Get-Date -Format 'yyyyMMddHHmmss')"

git checkout -b $temporaryBranch $tag
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось создать rollback-ветку."
}

try {
    & powershell.exe `
        -NoProfile `
        -ExecutionPolicy Bypass `
        -File (Join-Path $Root "deploy_vps.ps1") `
        -VpsHost $VpsHost `
        -VpsUser $VpsUser `
        -ExpectedVersion $Version

    if ($LASTEXITCODE -ne 0) {
        throw "Откат завершился с ошибкой."
    }

    Write-Host "VPS возвращён к Restaurant OS $Version." -ForegroundColor Green
}
finally {
    git checkout develop
    git branch -D $temporaryBranch
}
