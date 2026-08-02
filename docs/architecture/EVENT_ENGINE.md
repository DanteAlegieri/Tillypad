# Event Engine — Design Draft

## Цель

Сделать события постоянными объектами системы, а не временными карточками.

## Сущность Event

```text
id
agent_id
event_type
source
severity
title
description
payload_json
status
created_at
acknowledged_at
resolved_at
```

## Статусы

```text
NEW
ACTIVE
ACKNOWLEDGED
DONE
ARCHIVED
```

## Уровни

```text
INFO
ANALYTIC
OPPORTUNITY
WARNING
CRITICAL
```

## Источники

```text
manager
operations
marketing
technology
finance
delivery
purchasing
system
```

## Следующий спринт

1. Миграция таблицы.
2. Repository.
3. Rules.
4. REST API.
5. Activity Feed 2.0.
6. Lifecycle actions.
