param(
    [string]$Remote = "origin",
    [string]$DevelopBranch = "develop"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".git")) {
    throw "Запустите скрипт из корня локального Git-репозитория."
}

git status

$exists = git branch --list $DevelopBranch
if (-not $exists) {
    git checkout -b $DevelopBranch
    Write-Host "Создана ветка $DevelopBranch" -ForegroundColor Green
} else {
    git checkout $DevelopBranch
}

git add .
git commit -m "docs(project): establish Restaurant OS repository structure"

Write-Host ""
Write-Host "Следующая команда отправит ветку в GitHub:" -ForegroundColor Cyan
Write-Host "git push -u $Remote $DevelopBranch"
