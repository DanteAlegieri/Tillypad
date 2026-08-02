# Contributing

## Ветки

- `main` — рабочая стабильная версия.
- `develop` — интеграционная ветка.
- `feature/<name>` — новая функция.
- `fix/<name>` — исправление.
- `docs/<name>` — документация.

## Рабочий процесс

```bash
git checkout develop
git pull
git checkout -b feature/event-engine
```

После завершения:

```bash
git add .
git commit -m "feat(events): add event repository"
git push -u origin feature/event-engine
```

Затем создаётся Pull Request в `develop`.

## Формат коммитов

```text
feat(events): add event lifecycle
fix(gateway): preserve database during deploy
docs(architecture): describe AI Core
refactor(agent): unify config loading
test(events): add repository tests
```

## Перед Pull Request

- Python-код компилируется.
- Новый функционал имеет проверки.
- Секреты не попали в Git.
- CHANGELOG обновлён.
- Документация обновлена.
