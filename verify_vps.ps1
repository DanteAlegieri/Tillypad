param(
    [Parameter(Mandatory = $true)]
    [string]$VpsHost,

    [string]$VpsUser = "root",

    [int]$SshPort = 22,

    [string]$AdminToken = "",

    [string]$AgentId = "gastrodom3"
)

$ErrorActionPreference = "Stop"
$Target = "$VpsUser@$VpsHost"

$HealthJson = ssh -p $SshPort $Target `
    "curl --fail --silent http://127.0.0.1:8020/health"

$Health = $HealthJson | ConvertFrom-Json

Write-Host "Gateway:" -ForegroundColor Cyan
$Health | Format-List

if ($AdminToken) {
    $escapedToken = $AdminToken.Replace("'", "'\''")
    $escapedAgent = $AgentId.Replace("'", "'\''")

    Write-Host "Последний облачный снимок:" -ForegroundColor Cyan

    ssh -p $SshPort $Target `
        "curl --silent --fail -H 'X-Admin-Token: $escapedToken' 'http://127.0.0.1:8020/api/cloud/$escapedAgent/sales/latest'"
}
