# voice_recognition

Сервис асинхронной транскрипции аудио. Два движка распознавания. Архитектура DDD + DIP.

## Запуск и выкат

Сервис работает **на двух машинах одновременно**, и обе боевые. Локально в этой репе он не
поднимается: репа — только исходник.

- **Домашний Linux-сервер** — `faster-whisper` на CUDA, в docker. Обслуживает нынешних
  потребителей и гаситься не собирается.
  - `docker-compose.yml` — серверный compose, которым владеет репа: без блока `build`
    (собирает выкат), порт 8000 публикуется точечно, модели монтируются с сервера.
  - `Dockerfile` — multi-stage build: uv → builder → runtime, BuildKit с cache-mount'ами.
- **Mac mini** — `mlx-whisper` на Metal, нативный процесс под launchd, **вне docker**: GPU на
  macOS не пробрасывается ни в одну Linux-VM, в контейнере модель считала бы на CPU.

Выкат — скилл `/deploy`, одна точка входа с выбором цели:

- `uv run .claude/skills/deploy/scripts/deploy-prod.py` — домашний сервер (цель по умолчанию):
  исходники туда, сборка образа **там**, перезапуск сервиса, `/health`.
- `uv run .claude/skills/deploy/scripts/deploy-prod.py --target mini` — Mac mini: исходники в
  рабочую копию, доустановка зависимостей в `.venv`, `launchctl kickstart`, `/health`.

`.env`, веса моделей и (на mini) `.venv` с plist демона выкат не трогает. Подробности,
префлайт и маршрутизация (когда звать агента `devops`) — в `.claude/skills/deploy/SKILL.md`.

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
