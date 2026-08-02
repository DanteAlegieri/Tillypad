# Restaurant Gateway v1

Центральный WebSocket-сервер для Restaurant OS Agent.

## Возможности

- авторизация по `Agent ID` и API-ключу;
- постоянное WebSocket-подключение агента;
- heartbeat и статусы online/offline;
- реестр ресторанов в SQLite;
- отправка разрешённых именованных запросов агенту;
- получение результата SQL-запроса через Gateway;
- административный REST API;
- запуск напрямую или через Docker.

## 1. Запуск локально

```powershell
cd gateway
$env:GATEWAY_ADMIN_TOKEN="сложный-длинный-токен"
.\run_gateway.ps1
```

Проверка:

```text
http://127.0.0.1:8020/health
```

Документация API:

```text
http://127.0.0.1:8020/docs
```

## 2. Создание ресторана

```powershell
$headers = @{
  "X-Admin-Token" = "сложный-длинный-токен"
}

$body = @{
  agent_id = "gastrodom3-main"
  name = "Гастродом №3"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8020/api/admin/agents" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body
```

Ответ содержит:

```json
{
  "agent_id": "gastrodom3-main",
  "name": "Гастродом №3",
  "api_key": "..."
}
```

API-ключ показывается при создании. Сохраните его.

## 3. Настройка агента

В Agent Manager:

```text
Agent ID: gastrodom3-main
WebSocket Gateway: ws://IP_СЕРВЕРА:8020/ws/agent
API-ключ: ключ из предыдущего шага
```

Для сервера с HTTPS:

```text
wss://gateway.example.ru/ws/agent
```

## 4. Проверка статуса

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8020/api/admin/agents" `
  -Headers $headers
```

## 5. Выполнение запроса через агента

```powershell
$body = @{
  query_name = "health_check"
  parameters = @{}
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8020/api/agents/gastrodom3-main/query" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body
```

Разрешённые запросы задаются на стороне агента в `QueryRegistry`.
Произвольный SQL через Gateway не принимается.

## Безопасность

Для разработки допустим `ws://` в локальной сети. Для интернета нужен:

- домен;
- HTTPS-сертификат;
- обратный прокси Nginx/Caddy;
- `wss://`;
- сложный `GATEWAY_ADMIN_TOKEN`;
- закрытый административный API.


## Gateway v1.1 / Agent v16.3

Добавлено:

- TTL-кэш результатов на агенте;
- `bypass_cache` и `cache_ttl_seconds` в API запроса;
- gzip+base64 для больших результатов;
- автоматическая распаковка на Gateway;
- получение разрешённых запросов агента;
- удалённая очистка кэша;
- хранение возможностей, версии, последнего запроса и размера кэша;
- готовый сценарий `test_agent_query.ps1`.

### Проверка рабочего обмена

```powershell
cd C:\TillypadDashboard\gateway

$env:GATEWAY_ADMIN_TOKEN="тот-же-токен"
.\test_agent_query.ps1 `
  -AgentId "gastrodom3" `
  -DateFrom "2026-08-02" `
  -DateTo "2026-08-02"
```

### Доступные именованные запросы

- `health_check`;
- `sales_summary`;
- `sales_hourly`;
- `menu_items`;
- `delivery_summary`;
- `basket_pairs`.

Произвольный SQL по Gateway по-прежнему запрещён.

### Очистка кэша

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8020/api/agents/gastrodom3/cache/clear" `
  -Headers $headers
```
