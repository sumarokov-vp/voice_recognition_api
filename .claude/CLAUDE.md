# voice_recognition

Сервис асинхронной транскрипции аудио на базе faster-whisper. Архитектура DDD + DIP.

## Запуск и выкат

Сервис работает в Docker на отдельной машине с GPU. Локально в этой репе он не
поднимается и рабочей копии на сервере больше нет: репа — только исходник.

- `docker-compose.yml` — серверный compose, которым владеет репа: без блока `build`
  (собирает выкат), порт 8000 публикуется точечно, модели монтируются с сервера.
- `Dockerfile` — multi-stage build: uv → builder → runtime, BuildKit с cache-mount'ами.

Выкат — скилл `/deploy`: `uv run .claude/skills/deploy/scripts/deploy-prod.py`. Он копирует
исходники на сервер, собирает образ **там**, перезапускает сервис из его каталога и
проверяет `/health`. `.env` и `models/` на сервере не трогает. Подробности, префлайт и
маршрутизация (когда звать агента `devops`) — в `.claude/skills/deploy/SKILL.md`.

## Структура

```
src/
  api/               # HTTP-слой (FastAPI)
    composition/     # Composition root
    protocols/       # Контракты use cases для API
    routes/          # Роуты
    schemas/         # Pydantic-схемы
  transcription/     # Домен транскрипции
    domain/          # Сущности, исключения, статусы
    application/     # Use cases, протоколы
    infrastructure/  # Реализации (whisper engine, репозитории)
```

## Технологии

- Python 3.14, FastAPI, uv
- faster-whisper (NVIDIA GPU, CUDA)
- In-memory хранилище задач (при рестарте задачи теряются)
