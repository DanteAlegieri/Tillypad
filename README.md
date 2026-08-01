# Tillypad Dashboard v1.2

Первая стабильная архитектурная версия проекта для «Гастродома №3».

## Возможности

- прямое подключение к SQL Server Tillypad через Radmin VPN;
- SQL-дашборд по таблице `dbo.tp_Guests`;
- SQL Explorer:
  - поиск таблиц;
  - количество строк;
  - поиск колонок;
  - структура таблицы;
  - безопасный `SELECT TOP`;
- логирование;
- настройки через `.env`;
- разделение кода на:
  - подключение к БД;
  - репозитории;
  - сервисы;
  - веб-маршруты;
  - шаблоны.

Все SQL-запросы используют только `SELECT`.

## Установка

1. Сохраните старый файл `.env`.
2. Распакуйте архив в:

```text
C:\TillypadDashboard
```

3. Скопируйте `.env.example` в `.env`.
4. Заполните:

```env
TILLYPAD_SQL_SERVER=26.187.75.193
TILLYPAD_SQL_PORT=1433
TILLYPAD_SQL_DATABASE=TillypadSegment
TILLYPAD_SQL_USER=ваш_sql_логин
TILLYPAD_SQL_PASSWORD=ваш_sql_пароль
TILLYPAD_SQL_DRIVER=ODBC Driver 18 for SQL Server
TILLYPAD_SQL_ENCRYPT=no
TILLYPAD_SQL_TRUST_CERTIFICATE=yes
TILLYPAD_SQL_TIMEOUT=10
```

5. Запустите `install.bat`.
6. Запустите `run.bat`.

## Адреса

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/sql
http://127.0.0.1:8000/sql-explorer
http://127.0.0.1:8000/sql-test
```

## Git

```cmd
git add .
git commit -m "Release stable architecture v1.2"
git push
```


## Карта базы

Страница: `http://127.0.0.1:8000/schema-map`

Показывает таблицы, колонки, первичные и внешние ключи и фильтрацию по ключевым словам.


## Продажи

Новая страница:

```text
http://127.0.0.1:8000/sales
```

Показывает:

- выручку за выбранный период;
- количество чеков;
- средний чек;
- количество проданных единиц;
- продажи по часам;
- топ блюд;
- последние чеки.

Текущая формула:

```text
orit_Count × orit_Price
```

Пока отчёт не исключает отменённые позиции, возвраты и служебные движения.
Следующий этап — определить назначение `orit_mvtp_ID` и статусов заказа.
