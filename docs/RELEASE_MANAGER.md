# Release Manager v1.0

## Создание релиза

```powershell
.\scripts\release.ps1 `
  -Version 10.3.0 `
  -VpsHost 5.8.53.75 `
  -VpsUser root
```

Скрипт:

1. проверяет чистоту Git;
2. обновляет `develop`;
3. создаёт `release/X.Y.Z`;
4. обновляет версии;
5. проверяет Python и JavaScript;
6. собирает ZIP в `releases/X.Y.Z`;
7. делает commit и push;
8. деплоит на VPS;
9. проверяет `/health` и версию.

## Публикация после теста

```powershell
.\scripts\release.ps1 -Publish -PublishVersion 10.3.0
```

Публикация:

- сливает release-ветку в `main`;
- создаёт тег `vX.Y.Z`;
- синхронизирует `develop`.

## Откат

```powershell
.\scripts\rollback.ps1 -Version 10.2.1
```

Откат разворачивает код из существующего Git-тега.
