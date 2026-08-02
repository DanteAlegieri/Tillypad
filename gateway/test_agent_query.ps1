param(
    [string]$AdminToken = $env:GATEWAY_ADMIN_TOKEN,
    [string]$AgentId = "gastrodom3",
    [string]$DateFrom = (Get-Date).ToString("yyyy-MM-dd"),
    [string]$DateTo = (Get-Date).ToString("yyyy-MM-dd")
)

if (-not $AdminToken) {
    throw "Укажите GATEWAY_ADMIN_TOKEN или параметр -AdminToken"
}

$headers = @{
    "X-Admin-Token" = $AdminToken
}

Write-Host "1. Список агентов" -ForegroundColor Cyan
Invoke-RestMethod `
    -Uri "http://127.0.0.1:8020/api/admin/agents" `
    -Headers $headers | Format-List

Write-Host "2. Возможности агента" -ForegroundColor Cyan
Invoke-RestMethod `
    -Uri "http://127.0.0.1:8020/api/agents/$AgentId/capabilities" `
    -Headers $headers | ConvertTo-Json -Depth 8

Write-Host "3. Проверка SQL через Gateway" -ForegroundColor Cyan
$healthBody = @{
    query_name = "health_check"
    parameters = @{}
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8020/api/agents/$AgentId/query" `
    -Headers $headers `
    -ContentType "application/json; charset=utf-8" `
    -Body $healthBody | ConvertTo-Json -Depth 8

Write-Host "4. Продажи за период" -ForegroundColor Cyan
$salesBody = @{
    query_name = "sales_summary"
    parameters = @{
        date_from = $DateFrom
        date_to = $DateTo
    }
    cache_ttl_seconds = 45
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8020/api/agents/$AgentId/query" `
    -Headers $headers `
    -ContentType "application/json; charset=utf-8" `
    -Body $salesBody | ConvertTo-Json -Depth 8
