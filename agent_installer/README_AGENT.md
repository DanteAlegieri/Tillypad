# Gastrodom Relay Agent — установка службы Windows

## Что делает установщик

- устанавливает агент в:
  `C:\Program Files\Gastrodom\RelayAgent`;
- создаёт скрытую защищённую папку:
  `C:\ProgramData\Gastrodom\RelayAgent`;
- создаёт изолированное Python-окружение;
- регистрирует службу Windows:
  `GastrodomRelayAgent`;
- включает автоматический запуск;
- настраивает автоматический перезапуск после сбоя;
- не создаёт ярлыков;
- не показывает консольное окно при работе.

## Установка

1. Установите Microsoft ODBC Driver 18 for SQL Server.
2. Распакуйте архив.
3. Откройте папку `agent_installer`.
4. Запустите от имени администратора:
   `install_relay_service.bat`.
5. Откройте:
   `C:\ProgramData\Gastrodom\RelayAgent\agent.env`.
6. Укажите SQL-сервер, readonly-пользователя и API-ключ.
7. Выполните от имени администратора:

```powershell
Restart-Service GastrodomRelayAgent
```

## Проверка

```powershell
Get-Service GastrodomRelayAgent
```

Локальная проверка API:

```powershell
$headers = @{"X-Relay-Key"="ВАШ_API_КЛЮЧ"}
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8010/v1/health" `
  -Headers $headers
```

## Доступ с другого компьютера

По умолчанию агент слушает только `127.0.0.1`.

Для сетевого доступа:

1. в `agent.env` установите:
   `RELAY_AGENT_HOST=0.0.0.0`;
2. перезапустите службу;
3. разрешите вход только от IP-адреса Restaurant OS;
4. предпочтительно используйте HTTPS reverse proxy или защищённый туннель.

Не открывайте порт агента всему интернету.

## Где находятся данные

- программа:
  `C:\Program Files\Gastrodom\RelayAgent`;
- конфигурация:
  `C:\ProgramData\Gastrodom\RelayAgent\agent.env`;
- журналы:
  `C:\ProgramData\Gastrodom\RelayAgent\logs`;
- кэш:
  `C:\ProgramData\Gastrodom\RelayAgent\cache`.

Обычным пользователям папка ProgramData агента недоступна.
Администратор компьютера всегда сможет увидеть установленную службу.
