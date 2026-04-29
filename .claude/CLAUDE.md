# voice_recognition

Сервис асинхронной транскрипции аудио на базе faster-whisper. Архитектура DDD + DIP.

## Запуск

Сервис работает в Docker. Не запускается локально напрямую.

- `docker-compose.yml` — конфигурация контейнера (порт 8000, GPU, модели в `./data/models`)
- `Dockerfile` — multi-stage build: uv → builder → runtime

Для деплоя используй скилл `/deploy`.

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
