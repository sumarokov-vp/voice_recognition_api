# voice_recognition

Локальный сервис распознавания голосовых сообщений на базе
[`faster-whisper`](https://github.com/SYSTRAN/faster-whisper). Поднимается в
Docker, предоставляет HTTP API, к которому подключаются локальные боты через
тонкий клиентский SDK.

Детали архитектуры — в [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## Структура

```
src/
  transcription/    # Ядро: домен + use case + faster-whisper движок
  api/              # HTTP-слой: FastAPI, роуты, DI, composition root
  client/           # SDK: Protocol ITranscriber + httpx-реализация
tests/              # Smoke-тесты use case и клиента
```

## Запуск

1. Скопировать пример окружения и при необходимости отредактировать:

   ```bash
   cp .env.example .env
   ```

2. Собрать и запустить контейнер:

   ```bash
   docker compose build
   docker compose up -d
   ```

3. Проверить работоспособность:

   ```bash
   curl http://localhost:8000/health
   curl -X POST http://localhost:8000/transcribe \
        -F "file=@voice.ogg" \
        -F "language=ru"
   ```

## Конфигурация

Переменная              | По умолчанию | Назначение
------------------------|--------------|-----------------------------------------------
`WHISPER_MODEL`         | `small`      | Размер модели (`tiny`, `base`, `small`, `medium`, `large-v3`)
`WHISPER_DEVICE`        | `cpu`        | `cpu` или `cuda`
`WHISPER_COMPUTE_TYPE`  | `int8`       | Тип весов (`int8`, `float16`, `float32`)
`WHISPER_LANGUAGE`      | `ru`         | Дефолтный язык (`auto` — автоопределение)
`WHISPER_MODEL_DIR`     | `/models`    | Путь для кеша моделей внутри контейнера
`API_HOST`              | `0.0.0.0`    | Адрес для bind
`API_PORT`              | `8000`       | Порт
`MAX_FILE_SIZE_MB`      | `25`         | Максимальный размер загружаемого файла

Модель кешируется в томе `./data/models:/models`.

## HTTP API

### `POST /transcribe`

`multipart/form-data`:

- `file` — аудио (ogg/opus/mp3/wav/m4a)
- `language` (optional) — `ru`, `en`, `auto`, ...
- лимит 25 МБ

Ответ:

```json
{
  "text": "...",
  "language": "ru",
  "duration": 3.2,
  "segments": [{"start": 0.0, "end": 1.5, "text": "..."}]
}
```

### `GET /health`

```json
{"status": "ok", "model": "small", "device": "cpu", "loaded": true}
```

## Подключение клиента в боте

Добавить в бота SDK как editable-пакет (если монорепо/локальная разработка):

```bash
uv add --editable /home/sumarokov/projects/infrastructure/voice_recognition
```

Использование:

```python
from pathlib import Path

from client import HttpTranscriber, HttpTranscriberConfig, TextTranscriberAdapter

http_transcriber = HttpTranscriber(
    HttpTranscriberConfig(base_url="http://voice-recognition:8000"),
)

# Вариант 1: нативный API — полный результат
result = http_transcriber.transcribe(Path("/tmp/voice.ogg"))
print(result.text, result.segments)

# Вариант 2: адаптер для обратной совместимости с прежним ITranscriber
legacy_transcriber = TextTranscriberAdapter(http_transcriber)
text: str = legacy_transcriber.transcribe(Path("/tmp/voice.ogg"))
```

`Protocol ITranscriber` импортируется из `client.protocols.i_transcriber`.
Боты объявляют зависимость от этого протокола, а в composition root бота
подставляется либо `HttpTranscriber` (новые потребители), либо
`TextTranscriberAdapter` (старые потребители, ожидающие `str`).

## Разработка

```bash
uv sync --all-extras
uv run pytest
uv run ruff check src tests
uv run mypy
uv run lint-imports
```
