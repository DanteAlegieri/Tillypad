# Architecture

## Контуры

### Restaurant Site

- TillyPad SQL Server
- Restaurant OS Agent
- Local diagnostics UI

### Cloud

- Gateway
- Storage
- AI Core
- Recommendation Engine
- Owner Cabinet

## Поток данных

```mermaid
sequenceDiagram
    participant T as TillyPad SQL
    participant A as Agent
    participant G as Gateway
    participant S as Storage
    participant AI as AI Core
    participant W as Web Cabinet

    A->>T: Named SQL queries
    T-->>A: Sales data
    A->>G: WebSocket cloud snapshot
    G->>S: Persist snapshot
    W->>G: Request dashboard data
    G->>AI: Build report
    AI-->>G: Briefing and recommendations
    G-->>W: JSON response
```

## Архитектурные ограничения

- Произвольный SQL через Gateway запрещён.
- Agent инициирует только исходящее соединение.
- Секреты не хранятся в Git.
- UI не содержит бизнес-правила.
- Рекомендации формируются серверным AI Core.
