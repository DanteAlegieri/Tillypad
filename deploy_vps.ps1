param(
    [Parameter(Mandatory = $true)]
    [string]$VpsHost,

    [string]$VpsUser = "root",

    [string]$RemotePath = "/opt/restaurantos/gateway",

    [string]$ExpectedVersion = "9.1.0",

    [string]$SshKey = "",

    [int]$SshPort = 22
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$GatewaySource = Join-Path $ProjectRoot "gateway"

if (-not (Test-Path $GatewaySource)) {
    throw "Папка gateway не найдена: $GatewaySource"
}

function Test-CommandExists {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

foreach ($command in @("ssh", "scp")) {
    if (-not (Test-CommandExists $command)) {
        throw "Команда '$command' не найдена. Установите OpenSSH Client в Windows."
    }
}

$Target = "$VpsUser@$VpsHost"

$CommonSshArgs = @(
    "-p", "$SshPort",
    "-o", "ServerAliveInterval=15",
    "-o", "ServerAliveCountMax=4",
    "-o", "StrictHostKeyChecking=accept-new"
)

$CommonScpArgs = @(
    "-P", "$SshPort",
    "-o", "ServerAliveInterval=15",
    "-o", "ServerAliveCountMax=4",
    "-o", "StrictHostKeyChecking=accept-new"
)

if ($SshKey) {
    $ResolvedKey = (Resolve-Path $SshKey).Path
    $CommonSshArgs += @("-i", $ResolvedKey)
    $CommonScpArgs += @("-i", $ResolvedKey)
}

$ReleaseName = "restaurantos_gateway_release_$([DateTime]::UtcNow.ToString('yyyyMMdd_HHmmss'))"
$LocalRelease = Join-Path $env:TEMP $ReleaseName
$ArchivePath = "$LocalRelease.tar.gz"
$RemoteArchive = "/tmp/$ReleaseName.tar.gz"
$RemoteStaging = "/tmp/$ReleaseName"

Write-Host ""
Write-Host "Restaurant OS Gateway deployment" -ForegroundColor Cyan
Write-Host "VPS: $Target"
Write-Host "Путь: $RemotePath"
Write-Host "Ожидаемая версия: $ExpectedVersion"
Write-Host ""

try {
    Write-Host "[1/7] Проверка SSH..." -ForegroundColor Yellow
    & ssh @CommonSshArgs $Target "echo SSH_OK"
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось подключиться к VPS по SSH."
    }

    Write-Host "[2/7] Подготовка релиза..." -ForegroundColor Yellow
    if (Test-Path $LocalRelease) {
        Remove-Item $LocalRelease -Recurse -Force
    }
    New-Item -ItemType Directory -Path $LocalRelease | Out-Null

    Copy-Item `
        -Path (Join-Path $GatewaySource "*") `
        -Destination $LocalRelease `
        -Recurse `
        -Force

    # Локальные данные и секреты не должны перезаписывать VPS.
    foreach ($excluded in @(
        ".env",
        "gateway.db",
        "data",
        "__pycache__",
        ".git"
    )) {
        $path = Join-Path $LocalRelease $excluded
        if (Test-Path $path) {
            Remove-Item $path -Recurse -Force
        }
    }

    Write-Host "[3/7] Создание архива..." -ForegroundColor Yellow
    tar -czf $ArchivePath -C $LocalRelease .
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось создать архив Gateway."
    }

    Write-Host "[4/7] Копирование на VPS..." -ForegroundColor Yellow
    & scp @CommonScpArgs $ArchivePath "${Target}:$RemoteArchive"
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось скопировать релиз на VPS."
    }

    Write-Host "[5/7] Установка релиза..." -ForegroundColor Yellow

    $RemoteScript = @"
set -euo pipefail

REMOTE_PATH='$RemotePath'
REMOTE_STAGING='$RemoteStaging'
REMOTE_ARCHIVE='$RemoteArchive'

mkdir -p "`$REMOTE_STAGING"
tar -xzf "`$REMOTE_ARCHIVE" -C "`$REMOTE_STAGING"

mkdir -p "`$REMOTE_PATH"

if [ -f "`$REMOTE_PATH/.env" ]; then
    cp "`$REMOTE_PATH/.env" /tmp/restaurantos_gateway.env.backup
fi

if [ -d "`$REMOTE_PATH/data" ]; then
    cp -a "`$REMOTE_PATH/data" /tmp/restaurantos_gateway_data.backup
fi

find "`$REMOTE_PATH" -mindepth 1 -maxdepth 1 \
    ! -name '.env' \
    ! -name 'data' \
    -exec rm -rf {} +

cp -a "`$REMOTE_STAGING/." "`$REMOTE_PATH/"

if [ ! -f "`$REMOTE_PATH/.env" ] && \
   [ -f /tmp/restaurantos_gateway.env.backup ]; then
    cp /tmp/restaurantos_gateway.env.backup "`$REMOTE_PATH/.env"
fi

if [ ! -d "`$REMOTE_PATH/data" ] && \
   [ -d /tmp/restaurantos_gateway_data.backup ]; then
    cp -a /tmp/restaurantos_gateway_data.backup "`$REMOTE_PATH/data"
fi

mkdir -p "`$REMOTE_PATH/data"

cd "`$REMOTE_PATH"
docker compose up -d --build --remove-orphans

rm -rf "`$REMOTE_STAGING" "`$REMOTE_ARCHIVE"
"@

    $RemoteScript = $RemoteScript -replace "`r`n", "`n"

$RemoteScript | & ssh @CommonSshArgs $Target "bash -s"
    if ($LASTEXITCODE -ne 0) {
        throw "Ошибка развёртывания Gateway на VPS."
    }

    Write-Host "[6/7] Ожидание запуска..." -ForegroundColor Yellow
    Start-Sleep -Seconds 4

    $HealthJson = & ssh @CommonSshArgs $Target `
        "curl --fail --silent http://127.0.0.1:8020/health"
    if ($LASTEXITCODE -ne 0) {
        throw "Gateway запущен, но /health не отвечает."
    }

    $Health = $HealthJson | ConvertFrom-Json
    if (-not $Health.ok) {
        throw "Gateway вернул отрицательный health status."
    }

    if ([string]$Health.version -ne $ExpectedVersion) {
        throw (
            "Версия Gateway не совпала. " +
            "Ожидалась $ExpectedVersion, получена $($Health.version)."
        )
    }

    Write-Host "[7/7] Проверка контейнера..." -ForegroundColor Yellow
    & ssh @CommonSshArgs $Target `
        "cd '$RemotePath' && docker compose ps"

    Write-Host ""
    Write-Host "Deployment successful" -ForegroundColor Green
    Write-Host "Gateway version: $($Health.version)" -ForegroundColor Green
    Write-Host "Online agents: $($Health.online_agents)" -ForegroundColor Green
}
finally {
    if (Test-Path $LocalRelease) {
        Remove-Item $LocalRelease -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $ArchivePath) {
        Remove-Item $ArchivePath -Force -ErrorAction SilentlyContinue
    }
}
