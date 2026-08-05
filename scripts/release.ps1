[CmdletBinding(DefaultParameterSetName = "Create")]
param(
    [Parameter(ParameterSetName = "Create", Mandatory = $true)]
    [string]$Version,

    [Parameter(ParameterSetName = "Publish", Mandatory = $true)]
    [switch]$Publish,

    [Parameter(ParameterSetName = "Publish", Mandatory = $true)]
    [string]$PublishVersion,

    [Parameter(ParameterSetName = "Create")]
    [string]$VpsHost = "5.8.53.75",

    [Parameter(ParameterSetName = "Create")]
    [string]$VpsUser = "root",

    [Parameter(ParameterSetName = "Create")]
    [switch]$SkipDeploy,

    [Parameter(ParameterSetName = "Create")]
    [switch]$SkipPush
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Write-Step {
    param([string]$Text)
    Write-Host ""
    Write-Host $Text -ForegroundColor Yellow
}

function Run-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & git @Args
    if ($LASTEXITCODE -ne 0) {
        throw "Git завершился с ошибкой: git $($Args -join ' ')"
    }
}

function Assert-CleanWorkingTree {
    $status = git status --porcelain
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось проверить git status."
    }

    if ($status) {
        Write-Host $status
        throw "Рабочая копия содержит незакоммиченные изменения."
    }
}

function Assert-BranchExists {
    param([string]$Branch)
    git show-ref --verify --quiet "refs/heads/$Branch"
    if ($LASTEXITCODE -ne 0) {
        throw "Локальная ветка '$Branch' не найдена."
    }
}

function Test-Version {
    param([string]$Value)
    if ($Value -notmatch '^\d+\.\d+\.\d+$') {
        throw "Версия должна иметь формат X.Y.Z."
    }
}

function Update-VersionFiles {
    param([string]$NewVersion)

    $utf8 = New-Object System.Text.UTF8Encoding($false)

    $files = @(
        "gateway/app/main.py",
        "gateway/app/owner_dashboard.py",
        "deploy_vps.ps1",
        "deploy_vps_example.ps1"
    )

    foreach ($relativePath in $files) {
        $path = Join-Path $Root $relativePath
        if (-not (Test-Path $path)) {
            throw "Не найден файл версии: $relativePath"
        }

        $text = [System.IO.File]::ReadAllText($path)
        $text = [regex]::Replace(
            $text,
            'version="\d+\.\d+\.\d+"',
            "version=`"$NewVersion`"",
            1
        )
        $text = [regex]::Replace(
            $text,
            '"version": "\d+\.\d+\.\d+"',
            "`"version`": `"$NewVersion`"",
            1
        )
        $text = [regex]::Replace(
            $text,
            '"app_version": "\d+\.\d+\.\d+"',
            "`"app_version`": `"$NewVersion`""
        )
        $text = [regex]::Replace(
            $text,
            'ExpectedVersion = "\d+\.\d+\.\d+"',
            "ExpectedVersion = `"$NewVersion`""
        )
        $text = [regex]::Replace(
            $text,
            '-ExpectedVersion "\d+\.\d+\.\d+"',
            "-ExpectedVersion `"$NewVersion`""
        )
        [System.IO.File]::WriteAllText($path, $text, $utf8)
    }

    $templateFiles = Get-ChildItem `
        -Path (Join-Path $Root "gateway/app/templates") `
        -Filter "*.html" `
        -Recurse

    foreach ($file in $templateFiles) {
        $text = [System.IO.File]::ReadAllText($file.FullName)
        $text = [regex]::Replace(
            $text,
            '(\?v=)\d+\.\d+\.\d+',
            "`${1}$NewVersion"
        )
        [System.IO.File]::WriteAllText($file.FullName, $text, $utf8)
    }

    $releaseVersion = @"
Restaurant OS $NewVersion
Gateway $NewVersion
Agent 31.1.0
Managed by Release Manager v1.0
"@
    [System.IO.File]::WriteAllText(
        (Join-Path $Root "RELEASE_VERSION.txt"),
        $releaseVersion,
        $utf8
    )
}

function Invoke-QualityChecks {
    Write-Step "[3/8] Проверка Python..."
    $pythonCode = @'
import ast
from pathlib import Path

root = Path(".")
files = list(root.rglob("*.py"))
for path in files:
    if ".git" in path.parts or "__pycache__" in path.parts:
        continue
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
print(f"Python OK: {len(files)} файлов")
'@
    $pythonCode | python -
    if ($LASTEXITCODE -ne 0) {
        throw "Проверка Python не пройдена."
    }

    Write-Step "[4/8] Проверка JavaScript..."
    $jsFiles = Get-ChildItem `
        -Path (Join-Path $Root "gateway/app/static/js") `
        -Filter "*.js" `
        -Recurse

    foreach ($file in $jsFiles) {
        & node --check $file.FullName
        if ($LASTEXITCODE -ne 0) {
            throw "Ошибка JavaScript: $($file.FullName)"
        }
    }

    Write-Host "JavaScript OK: $($jsFiles.Count) файлов" -ForegroundColor Green
}

function Build-ReleaseArchive {
    param([string]$ReleaseVersion)

    Write-Step "[5/8] Сборка ZIP..."

    $outputDirectory = Join-Path $Root "releases/$ReleaseVersion"
    New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

    $archivePath = Join-Path `
        $outputDirectory `
        "restaurant_os_$($ReleaseVersion.Replace('.', '_')).zip"

    if (Test-Path $archivePath) {
        Remove-Item $archivePath -Force
    }

    $excludeNames = @(
        ".git",
        "__pycache__",
        ".pytest_cache",
        "releases"
    )

    $staging = Join-Path $env:TEMP "restaurant_os_release_$ReleaseVersion"
    if (Test-Path $staging) {
        Remove-Item $staging -Recurse -Force
    }
    New-Item -ItemType Directory -Path $staging | Out-Null

    Get-ChildItem -Path $Root -Force | ForEach-Object {
        if ($excludeNames -notcontains $_.Name) {
            Copy-Item $_.FullName $staging -Recurse -Force
        }
    }

    Compress-Archive `
        -Path (Join-Path $staging "*") `
        -DestinationPath $archivePath `
        -CompressionLevel Optimal

    Remove-Item $staging -Recurse -Force

    $notesPath = Join-Path $outputDirectory "RELEASE.md"
    @"
# Restaurant OS $ReleaseVersion

Дата: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

Ветка: release/$ReleaseVersion

Артефакт:
$([System.IO.Path]::GetFileName($archivePath))
"@ | Set-Content -Path $notesPath -Encoding utf8

    return $archivePath
}

function Deploy-Release {
    param(
        [string]$ReleaseVersion,
        [string]$HostName,
        [string]$UserName
    )

    Write-Step "[7/8] Деплой на VPS..."

    & powershell.exe `
        -NoProfile `
        -ExecutionPolicy Bypass `
        -File (Join-Path $Root "deploy_vps.ps1") `
        -VpsHost $HostName `
        -VpsUser $UserName `
        -ExpectedVersion $ReleaseVersion

    if ($LASTEXITCODE -ne 0) {
        throw "Деплой завершился с ошибкой."
    }

    Write-Step "[8/8] Финальная проверка Gateway..."

    $target = "$UserName@$HostName"
    $healthJson = ssh $target `
        "curl -fsS http://127.0.0.1:8020/health"

    if ($LASTEXITCODE -ne 0 -or -not $healthJson) {
        throw "Gateway не отвечает после деплоя."
    }

    $health = $healthJson | ConvertFrom-Json

    if (-not $health.ok) {
        throw "Gateway вернул отрицательный health status."
    }

    if ($health.version -ne $ReleaseVersion) {
        throw "Версия на VPS не совпала. Ожидалась $ReleaseVersion, получена $($health.version)."
    }
}

function Create-Release {
    param([string]$ReleaseVersion)

    Test-Version $ReleaseVersion

    Write-Step "[1/8] Проверка Git..."
    Assert-CleanWorkingTree

    Run-Git checkout develop
    Run-Git pull origin develop

    $releaseBranch = "release/$ReleaseVersion"

    git show-ref --verify --quiet "refs/heads/$releaseBranch"
    if ($LASTEXITCODE -eq 0) {
        throw "Ветка $releaseBranch уже существует."
    }

    Run-Git checkout -b $releaseBranch

    Write-Step "[2/8] Обновление версии..."
    Update-VersionFiles $ReleaseVersion

    Invoke-QualityChecks

    $archivePath = Build-ReleaseArchive $ReleaseVersion

    Write-Step "[6/8] Commit и Push..."
    Run-Git add .
    Run-Git commit -m "release: Restaurant OS $ReleaseVersion"

    if (-not $SkipPush) {
        Run-Git push -u origin $releaseBranch
    }
    else {
        Write-Host "Push пропущен параметром -SkipPush." -ForegroundColor DarkYellow
    }

    if (-not $SkipDeploy) {
        Deploy-Release `
            -ReleaseVersion $ReleaseVersion `
            -HostName $VpsHost `
            -UserName $VpsUser
    }
    else {
        Write-Host "Деплой пропущен параметром -SkipDeploy." -ForegroundColor DarkYellow
    }

    Write-Host ""
    Write-Host "Restaurant OS $ReleaseVersion подготовлен." -ForegroundColor Green
    Write-Host "Ветка: $releaseBranch"
    Write-Host "Артефакт: $archivePath"
    if (-not $SkipDeploy) {
        Write-Host "URL: http://$VpsHost`:8020/dashboard"
    }
    Write-Host ""
    Write-Host "После ручной проверки:"
    Write-Host ".\scripts\release.ps1 -Publish -PublishVersion $ReleaseVersion"
}

function Publish-Release {
    param([string]$ReleaseVersion)

    Test-Version $ReleaseVersion
    Assert-CleanWorkingTree

    $releaseBranch = "release/$ReleaseVersion"

    Write-Step "[1/6] Проверка веток..."
    Run-Git fetch origin
    Assert-BranchExists $releaseBranch
    Assert-BranchExists main
    Assert-BranchExists develop

    Write-Step "[2/6] Merge в main..."
    Run-Git checkout main
    Run-Git pull origin main
    Run-Git merge --no-ff $releaseBranch -m "merge: Restaurant OS $ReleaseVersion"
    Run-Git push origin main

    Write-Step "[3/6] Создание тега..."
    git tag --list "v$ReleaseVersion"
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось проверить тег."
    }

    $existingTag = git tag --list "v$ReleaseVersion"
    if (-not $existingTag) {
        Run-Git tag -a "v$ReleaseVersion" -m "Restaurant OS $ReleaseVersion"
        Run-Git push origin "v$ReleaseVersion"
    }

    Write-Step "[4/6] Обновление develop..."
    Run-Git checkout develop
    Run-Git pull origin develop
    Run-Git merge --no-ff main -m "sync: main after $ReleaseVersion"
    Run-Git push origin develop

    Write-Step "[5/6] Проверка опубликованной версии..."
    $mainVersion = git show "main:RELEASE_VERSION.txt"
    if ($LASTEXITCODE -ne 0 -or $mainVersion -notmatch [regex]::Escape($ReleaseVersion)) {
        throw "В main не подтверждена версия $ReleaseVersion."
    }

    Write-Step "[6/6] Завершение..."
    Write-Host "Restaurant OS $ReleaseVersion опубликован." -ForegroundColor Green
    Write-Host "main обновлён"
    Write-Host "develop синхронизирован"
    Write-Host "tag v$ReleaseVersion создан"
}

if ($PSCmdlet.ParameterSetName -eq "Publish") {
    Publish-Release $PublishVersion
}
else {
    Create-Release $Version
}
