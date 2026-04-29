# voice_recognition

HTTP-сервис транскрипции аудио на базе [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Принимает аудиофайл, возвращает текст с временными метками.

Работает на CPU или NVIDIA GPU (рекомендуется).

## Возможности

- Синхронная транскрипция — файл отправляется, ответ возвращается сразу
- Асинхронная транскрипция — задача ставится в очередь, результат забирается polling'ом
- Форматы: ogg, mp3, wav, m4a, opus и другие (через ffmpeg)
- Автоопределение языка
- GPU-ускорение через CUDA

## Требования

- Docker
- NVIDIA GPU + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) — для GPU-режима

## Быстрый старт

```bash
cp .env.example .env
docker compose up -d
```

Документация API доступна после запуска:

- **ReDoc** — http://localhost:8000/redoc
- **Swagger UI** — http://localhost:8000/docs

## Конфигурация

Переменные задаются в файле `.env`. Пример значений — в `.env.example`.

Переменная             | По умолчанию | Описание
-----------------------|--------------|------------------------------------------------------
`WHISPER_MODEL`        | `medium`     | Размер модели: `tiny`, `base`, `small`, `medium`, `large-v3`
`WHISPER_DEVICE`       | `cuda`       | Устройство: `cuda` или `cpu`
`WHISPER_COMPUTE_TYPE` | `float16`    | Точность: `float16`, `int8`, `float32`
`WHISPER_LANGUAGE`     | `ru`         | Язык по умолчанию (`auto` — автоопределение)
`WHISPER_MODEL_DIR`    | `/models`    | Путь кеша моделей внутри контейнера
`API_PORT`             | `8000`       | Порт сервиса
`MAX_FILE_SIZE_MB`     | `1000`       | Максимальный размер загружаемого файла, МБ

Модели кешируются в `./data/models` — при перезапуске контейнера не перекачиваются.

## API

Полная документация — [ReDoc](http://localhost:8000/redoc) или [Swagger UI](http://localhost:8000/docs).

### Синхронная транскрипция

```
POST /transcribe
```

Тело запроса: `multipart/form-data`

- `file` — аудиофайл
- `language` (необязательно) — код языка, например `ru`, `en`. По умолчанию берётся из конфига.

Пример:

```bash
curl -X POST http://localhost:8000/transcribe \
     -F "file=@audio.ogg"
```

### Асинхронная транскрипция

Подходит для больших файлов или когда не нужно ждать ответа.

```
POST /transcribe/async   — поставить задачу в очередь
GET  /transcribe/async/{job_id} — проверить статус и забрать результат
```

### Состояние сервиса

```
GET /health
```

## Клиентский SDK

В пакете есть готовый Python-клиент — `client`. Он не требует серверных зависимостей (только `httpx` и `pydantic`) и устанавливается напрямую из репозитория:

```bash
uv add "voice-recognition @ git+https://github.com/<org>/voice_recognition.git@v0.1.0"
```

Использование:

```python
from pathlib import Path
from client import HttpTranscriber, HttpTranscriberConfig

transcriber = HttpTranscriber(
    HttpTranscriberConfig(base_url="http://localhost:8000"),
)

result = transcriber.transcribe(Path("audio.ogg"))
print(result.text)
```
