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


## Режим WebSocket Gateway

В режиме WebSocket агент сам создаёт исходящее соединение:

```text
TillyPad Agent → WSS Gateway ← Restaurant OS
```

Преимущества:

- входящий порт на компьютере TillyPad не нужен;
- NAT и динамический IP не мешают;
- VPN не используется;
- соединение восстанавливается автоматически;
- heartbeat отправляется постоянно;
- сервер видит статус агента;
- разрешены только именованные запросы.

Запуск клиента вручную для проверки:

```powershell
C:\Program Files\Gastrodom\RelayAgent\.venv\Scripts\python.exe `
  -m app.websocket_agent_client
```

Для работы как служба следует заменить точку запуска службы
на `app.websocket_agent_client` или использовать отдельную службу,
созданную на его основе.


## Профессиональный установщик v15.3

В пакет добавлены:

- `agent_manager.py` — графическая панель настройки;
- проверка SQL Server;
- проверка интернета;
- проверка WebSocket Gateway;
- управление службой;
- экспорт диагностического отчёта без паролей;
- сценарий Inno Setup;
- сценарий сборки одного установщика.

### Сборка SetupAgent.exe на Windows

1. Установите Python 3.13 x64.
2. Установите Inno Setup 6.
3. Откройте PowerShell.
4. Выполните:

```powershell
cd agent_installer
.\build_setup.ps1
```

Готовый файл появится здесь:

```text
agent_installer\output\RestaurantOS_RelayAgent_Setup_15_3.exe
```

В этой поставке готовый EXE не скомпилирован и не подписан.


## v15.3.1 — Исправленный сценарий сборки Windows

Исправлено:

- скрипт автоматически использует `py`, `python` или `python3`;
- добавлена проверка наличия Python;
- добавлена попытка восстановления `pip` через `ensurepip`;
- русская консоль переключается на UTF-8;
- поддерживаются оба стандартных пути установки Inno Setup;
- после каждого этапа проверяется код завершения;
- ошибки содержат понятные инструкции по установке зависимостей.


## v15.3.2 — Исправление выбора Python

Исправлена ошибка PowerShell:

- ранее из строки `py` брался первый символ `p`;
- теперь команда `py`, `python` или `python3` используется целиком;
- строка `$Python[0]` удалена.


## v15.4 — автономный SetupAgent.exe без Inno Setup

Сборка больше не требует Inno Setup.

Сценарий `build_standalone_setup.ps1` создаёт три файла:

1. `AgentManager.exe` — настройка и диагностика;
2. `AgentService.exe` — скрытая служба Windows;
3. `RestaurantOS_Agent_Setup_15_4.exe` — единый установщик.

Установщик самостоятельно:

- запрашивает права администратора;
- создаёт `C:\Program Files\Gastrodom\RelayAgent`;
- создаёт скрытый защищённый каталог в `ProgramData`;
- копирует программу;
- сохраняет существующие настройки при обновлении;
- регистрирует службу Windows;
- включает автоматический запуск;
- включает восстановление после сбоев;
- запускает службу;
- открывает Agent Manager.

### Сборка

Запустите:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File "C:\TillypadDashboard\agent_installer\build_standalone_setup.ps1"
```

Либо двойным щелчком от администратора:

```text
agent_installer\build_standalone_setup.bat
```

Результат:

```text
C:\TillypadDashboard\dist\RestaurantOS_Agent_Setup_15_4.exe
```

Ограничение: полученный EXE не имеет цифровой подписи издателя.
Windows SmartScreen может показать предупреждение для нового файла.


## v15.5 — единый бинарник RestaurantOSAgent.exe

Теперь сборка создаёт только один передаваемый файл:

```text
dist\RestaurantOSAgent.exe
```

Один и тот же файл поддерживает режимы:

```text
RestaurantOSAgent.exe
```

Запускает установщик.

```text
RestaurantOSAgent.exe --config
```

Открывает панель настроек и диагностики.

```text
RestaurantOSAgent.exe --run-service
```

Используется службой Windows.

После установки файл копируется сюда:

```text
C:\Program Files\RestaurantOS\RestaurantOSAgent.exe
```

Отдельных `AgentManager.exe`, `AgentService.exe` и Inno Setup больше нет.

### Сборка

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File "C:\TillypadDashboard\agent_installer\build_single_agent.ps1"
```

Или:

```text
agent_installer\build_single_agent.bat
```

Результат:

```text
C:\TillypadDashboard\dist\RestaurantOSAgent.exe
```

Файл не подписан цифровой подписью, поэтому SmartScreen может показать предупреждение.


## v15.5.1 — регистрация службы через Windows Service API

Исправлена ошибка `Недопустимое поле start=`. Создание, запуск и удаление службы теперь выполняются напрямую через pywin32 (`CreateService`, `StartService`, `DeleteService`) без `sc.exe create`.


## v15.5.2 — исправление прав ProgramData

Исправлена ошибка:

```text
PermissionError: [WinError 5] Отказано в доступе:
C:\ProgramData\RestaurantOS\logs
```

Изменения:

- системные каталоги больше не создаются до запроса прав администратора;
- наследование ACL в `ProgramData\RestaurantOS` не отключается;
- `SYSTEM` и администраторы получают полный доступ;
- обычные пользователи получают права изменения конфигурации, кэша и логов;
- добавлен режим `--repair-permissions` для автоматического восстановления
  прав после установки v15.5.1;
- при обнаружении старых строгих прав Agent Manager сам запрашивает
  повышение прав и исправляет каталог.

Новый файл:

```text
dist\RestaurantOSAgent_15_5_2.exe
```


## v15.5.3 — универсальные права через SID

Исправлена повторная ошибка доступа:

```text
[WinError 5] Отказано в доступе:
C:\ProgramData\RestaurantOS\logs
```

Причина: имена групп `Users` и `Administrators` зависят от языка Windows.

Теперь используются универсальные SID:

- `S-1-5-18` — SYSTEM;
- `S-1-5-32-544` — администраторы;
- `S-1-5-32-545` — обычные пользователи;
- SID текущего пользователя определяется через Windows API.

Также добавлено:

- `takeown` перед восстановлением старых ACL;
- проверка результата `icacls`;
- восстановление прав до создания `logs` и `cache`;
- исправление папки от предыдущих версий при новой установке;
- отдельный режим `--repair-permissions`.

Новый файл:

```text
dist\RestaurantOSAgent_15_5_3.exe
```


## v15.6 — единый каталог без ProgramData

Все файлы агента теперь находятся в одном месте:

```text
C:\Program Files\RestaurantOS\
    RestaurantOSAgent.exe
    data\
        agent.env
        logs\
        cache\
```

Изменения:

- `C:\ProgramData\RestaurantOS` больше не используется;
- панель настроек всегда запрашивает права администратора;
- служба работает от SYSTEM и имеет доступ к данным;
- устранён конфликт старых ACL в ProgramData;
- при удалении агент пытается удалить старый каталог ProgramData;
- установка, служба и настройка остаются в одном EXE.

Новый файл:

```text
dist\RestaurantOSAgent_15_6_0.exe
```


## v16.0 — стабильный менеджер службы

Исправлена ошибка:

```text
module 'win32service' has no attribute 'DELETE'
```

Правильная константа:

```python
win32con.DELETE
```

Вся работа со службой вынесена в `app/service_manager.py`:

- установка;
- обновление поверх старой версии;
- запуск;
- остановка;
- перезапуск;
- удаление;
- чтение состояния;
- ожидание завершения остановки.

Новый файл после сборки:

```text
dist\RestaurantOSAgent_16_0_0.exe
```


## v16.1 — автоматическая первичная настройка SQL

Добавлено:

- определение установленных ODBC Driver for SQL Server;
- выпадающий список ODBC-драйверов;
- поиск локальных SQL Server и именованных экземпляров;
- чтение экземпляров SQL Server из реестра Windows;
- поиск доступных пользовательских баз;
- определение TillyPad по таблицам:
  - `dbo.orit`;
  - `dbo.ordr`;
  - `dbo.mitm`;
  - `dbo.tp_GuestDeliveries`;
- кнопка `Найти TillyPad автоматически`;
- автоматическое заполнение сервера, базы, порта и драйвера;
- понятный статус каждого этапа поиска.

Для автопоиска необходимо сначала ввести SQL-логин и пароль.

Регистрация по короткому коду подключения пока не реализована:
для неё требуется рабочий серверный API Gateway, который выдаёт
Agent ID и API-ключ.

Новый файл:

```text
dist\RestaurantOSAgent_16_1_0.exe
```


## v16.1.1 — безопасное обновление занятого EXE

Исправлена ошибка:

```text
[WinError 32] Процесс не может получить доступ к файлу,
так как этот файл занят другим процессом
```

Новый порядок обновления:

1. остановить старую службу;
2. удалить регистрацию старой службы;
3. дождаться освобождения файла;
4. скопировать новую версию во временный `.new.exe`;
5. атомарно заменить установленный EXE;
6. повторять замену до 20 раз с задержкой;
7. зарегистрировать и запустить новую службу;
8. открыть панель настройки только после завершения установки.

Новый файл:

```text
dist\RestaurantOSAgent_16_1_1.exe
```


## v17.0 — Agent v2 и локальный веб-интерфейс

Добавлено:

- явное состояние постоянного WebSocket-подключения;
- фиксация подключений, отключений и ошибок;
- автоматическое переподключение с отображением номера попытки;
- WebSocket ping/pong;
- heartbeat и отметка времени последней отправки;
- журнал `C:\Program Files\RestaurantOS\data\logs\agent.log`;
- файл состояния `runtime_state.json`;
- локальный веб-интерфейс:
  `http://127.0.0.1:8090`;
- JSON health endpoint:
  `http://127.0.0.1:8090/health`;
- API состояния и последних логов;
- кнопка локальной очистки кэша.

Веб-сервер слушает только `127.0.0.1`, поэтому не доступен
из внешней сети.

После установки:

```powershell
Invoke-RestMethod http://127.0.0.1:8090/health
```

Новый установочный файл:

```text
dist\RestaurantOSAgent_17_0_0.exe
```


## v18.0 — единая конфигурация

Исправлен главный дефект v17: GUI, служба и веб-интерфейс
теперь используют один и тот же `agent.env`.

Архитектура:

```text
agent.env
   └── AgentConfig
       ├── GUI
       ├── Windows Service
       ├── WebSocket Client
       └── Local Web UI
```

Добавлено:

- единый `AgentConfig`;
- принудительная загрузка `agent.env` до запуска службы;
- запрет использования старых Agent ID и Gateway из
  `runtime_state.json`;
- горячее перечитывание настроек;
- файл-команда `reload_config.request`;
- автоматическое перечитывание после нажатия `Сохранить`;
- кнопка `Перечитать настройки` в локальном Web UI;
- отображение фактического пути к `agent.env`;
- обновление WebSocket-клиента без переустановки.

Проверка после установки:

```powershell
Invoke-RestMethod http://127.0.0.1:8090/api/status
```

Должны отображаться:

```text
agent_id: gastrodom3
gateway_url: ws://5.8.53.75:8020/ws/agent
```

Новый файл:

```text
dist\RestaurantOSAgent_18_0_0.exe
```


## v19.0 — автоматическая облачная синхронизация

Агент автоматически каждые 5 минут отправляет на Gateway:

- дату;
- текущую выручку;
- количество чеков;
- средний чек;
- продажи по часам;
- время формирования снимка.

Gateway сохраняет историю в SQLite. Это первый этап
отделения Dashboard от прямых SQL-запросов.

Новые API Gateway:

```text
GET /api/cloud/{agent_id}/sales/latest
GET /api/cloud/{agent_id}/sales/history?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
```

Настройка интервала агента:

```env
TILLYPAD_CLOUD_SYNC_SECONDS=300
```

После обновления Gateway и установки агента первый снимок
отправляется примерно через 3 секунды после подключения.
