param(
    [string]$ReleaseBranch = "release/8.1.2",
    [string]$DevelopBranch = "develop",
    [switch]$UpdateMain
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    param(
        [Parameter(
            Mandatory = $true,
            Position = 0,
            ValueFromRemainingArguments = $true
        )]
        [string[]]$GitArguments
    )

    & git @GitArguments

    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git $($GitArguments -join ' ')"
    }
}

Write-Host "[1/8] Проверка репозитория..." -ForegroundColor Yellow
if (-not (Test-Path ".git")) {
    throw "Запусти скрипт из корня C:\TillypadDashboard"
}

$status = git status --porcelain
if ($status) {
    Write-Host "Обнаружены изменения релиза — они будут зафиксированы:" -ForegroundColor Cyan
    git status --short
} else {
    Write-Host "Локальных изменений нет." -ForegroundColor DarkYellow
}

Write-Host "[2/8] Получение веток с GitHub..." -ForegroundColor Yellow
Invoke-Git fetch origin --prune

$current = (git branch --show-current).Trim()
Write-Host "Текущая ветка: $current"

Write-Host "[3/8] Создание чистой релизной ветки..." -ForegroundColor Yellow
$remoteRelease = "origin/$ReleaseBranch"
$remoteExists = git ls-remote --heads origin $ReleaseBranch

if ($remoteExists) {
    Invoke-Git checkout -B $ReleaseBranch $remoteRelease
} else {
    Invoke-Git checkout -B $ReleaseBranch
}

Write-Host "[4/8] Добавление файлов релиза..." -ForegroundColor Yellow
Invoke-Git add -A

$staged = git diff --cached --name-only
if ($staged) {
    Invoke-Git commit -m "release: Restaurant OS 8.1.2 clean git baseline"
} else {
    Write-Host "Новых изменений для коммита нет." -ForegroundColor DarkYellow
}

Write-Host "[5/8] Публикация релизной ветки..." -ForegroundColor Yellow
Invoke-Git push -u origin $ReleaseBranch --force-with-lease

Write-Host "[6/8] Обновление develop..." -ForegroundColor Yellow
$developExists = git ls-remote --heads origin $DevelopBranch
if ($developExists) {
    Invoke-Git checkout $DevelopBranch
    Invoke-Git pull --ff-only origin $DevelopBranch
} else {
    Invoke-Git checkout -B $DevelopBranch
}

Invoke-Git merge --no-ff $ReleaseBranch -m "merge: Restaurant OS 8.1.2"
Invoke-Git push -u origin $DevelopBranch

if ($UpdateMain) {
    Write-Host "[7/8] Обновление main..." -ForegroundColor Yellow
    Invoke-Git checkout main
    Invoke-Git pull --ff-only origin main
    Invoke-Git merge --no-ff $DevelopBranch -m "release: Restaurant OS 8.1.2"
    Invoke-Git push origin main
} else {
    Write-Host "[7/8] main не изменён. Сначала проверь develop." -ForegroundColor DarkYellow
}

Write-Host "[8/8] Готово." -ForegroundColor Green
Write-Host "Релизная ветка: $ReleaseBranch"
Write-Host "Рабочая ветка: $DevelopBranch"
if (-not $UpdateMain) {
    Write-Host "После теста запусти:"
    Write-Host ".\scripts\align_git_release.ps1 -UpdateMain"
}
