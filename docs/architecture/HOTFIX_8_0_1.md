# Restaurant OS 8.0.1

Исправлен запуск Gateway после переноса Dashboard на Jinja2.

Причина: `Jinja2Templates` использовался приложением, но пакет `jinja2` отсутствовал в `gateway/requirements.txt`.

Dockerfile уже устанавливает этот файл и копирует всю папку `app`, поэтому шаблоны и статические ресурсы попадают в образ.
