# voice_recognition

HTTP-сервис транскрипции аудио на базе [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Принимает аудиофайл, возвращает текст с временными метками.

Работает на CPU или NVIDIA GPU (рекомендуется).

## Возможности

- Доступ по ключу — каждый потребитель ходит со своим `X-API-Key`, имя потребителя пишется в лог
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
# в .env заменить CHANGE_ME в API_KEYS на настоящий ключ
docker compose up -d
```

Без `API_KEYS` сервис не поднимается: молча открытый сервис хуже упавшего.

Документация API доступна после запуска — под тем же ключом, что и остальные ручки:

- **ReDoc** — http://localhost:8000/redoc
- **Swagger UI** — http://localhost:8000/docs

## Конфигурация

Переменные задаются в файле `.env`. Пример значений — в `.env.example`.

Переменная             | По умолчанию | Описание
-----------------------|--------------|------------------------------------------------------
`WHISPER_ENGINE`       | `faster`     | Движок распознавания: `faster` или `mlx` (см. ниже)
`WHISPER_LANGUAGE`     | `ru`         | Язык по умолчанию (`auto` — автоопределение)
`WHISPER_MODEL`        | `medium`     | Только `faster`. Размер модели: `tiny`, `base`, `small`, `medium`, `large-v3`
`WHISPER_DEVICE`       | `cuda`       | Только `faster`. Устройство: `cuda` или `cpu`
`WHISPER_COMPUTE_TYPE` | `float16`    | Только `faster`. Точность: `float16`, `int8`, `float32`
`WHISPER_MODEL_DIR`    | `/models`    | Только `faster`. Путь кеша моделей внутри контейнера
`WHISPER_MLX_MODEL`    | `mlx-community/whisper-large-v3-turbo` | Только `mlx`. Repo id модели на Hugging Face
`API_PORT`             | `8000`       | Порт сервиса
`MAX_FILE_SIZE_MB`     | `1000`       | Максимальный размер загружаемого файла, МБ
`API_KEYS`             | —            | Ключи потребителей: пары `имя:ключ` через запятую. Обязательна

Модели кешируются в `./data/models` — при перезапуске контейнера не перекачиваются.

Переменные чужого движка не удаляются и не ломают старт: движок берёт только свои,
а про остальные, если они заданы явно, пишет предупреждение в лог при старте.

## Движок распознавания

Переменная            | `faster` (по умолчанию)          | `mlx`
----------------------|----------------------------------|----------------------------------
Библиотека            | `faster-whisper` (ctranslate2)   | `mlx-whisper`
Железо                | NVIDIA CUDA или CPU              | Apple Silicon (GPU через Metal)
Запуск                | docker compose                   | нативно, вне docker
Установка             | `uv sync --extra server`         | `uv sync --extra server --extra mlx`
Модель                | `WHISPER_MODEL` + `WHISPER_MODEL_DIR` | `WHISPER_MLX_MODEL` (HF repo id)

`mlx` ставится только на macOS/arm64: у зависимости стоит маркер платформы, на Linux
группа `mlx` разрешается в пустой набор. Значение по умолчанию — `faster`, поэтому
обновление кода на Linux-сервере ничего не меняет.

Запуск на Apple Silicon:

```bash
brew install ffmpeg
uv sync --extra server --extra mlx
WHISPER_ENGINE=mlx uv run python -m api
```

Замеры на Mac mini M4 (45 секунд русской речи):

Модель                                     | Время  | Скорость
-------------------------------------------|--------|----------
`mlx-community/whisper-large-v3-mlx`       | 34.2 с | 1.3x
`mlx-community/whisper-large-v3-mlx-4bit`  | 21.5 с | 2.1x
`mlx-community/whisper-large-v3-turbo`     | 11.4 с | 3.9x (по умолчанию)

Веса модели скачиваются при старте сервиса, а не при первом запросе: движок
прогоняет через модель секунду тишины, чтобы `/health` не показывал готовность
раньше времени и чтобы первый запрос бота не ждал загрузку с Hugging Face.

## Доступ по ключу

Сервис отвечает только тому, кто предъявил ключ в заголовке `X-API-Key`.

- Ключи и имена потребителей задаются одной переменной `API_KEYS` — пары `имя:ключ`
  через запятую, например `voice_input:<ключ1>,ecto_bot:<ключ2>`. Имя нужно, чтобы по
  логу было видно, кто пришёл, и чтобы отобрать доступ у одного, не трогая остальных.
- Проверка стоит на всём приложении, а не на отдельных ручках: новая ручка закрыта
  по умолчанию. Открыт ровно один путь — `GET /health`, по нему живёт healthcheck
  контейнера. `/docs`, `/redoc` и `/openapi.json` — под ключом.
- Нет заголовка или ключ неизвестен — `401` с телом `{"detail": ...}`.
- На каждый пропущенный запрос в лог уходит строка с именем потребителя и путём.
  Сам ключ в лог не попадает ни при успехе, ни при отказе.
- Настоящие ключи в репозитории не лежат: в `.env.example` только имя переменной
  с заглушкой `CHANGE_ME`.

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
     -H "X-API-Key: $VOICE_RECOGNITION_API_KEY" \
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

Единственная ручка без ключа.

## Клиентский протокол

В пакете нет готового HTTP-клиента — только контракт `ITranscriber` и DTO ответа. Реализацию пишите у себя: это позволяет выбрать любую HTTP-библиотеку (`httpx`, `aiohttp`, `requests`) и не тащить лишние транзитивные зависимости.

### Пример HTTP-реализации

```python
import os
from pathlib import Path

import httpx
from pydantic import BaseModel


class Segment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptionResult(BaseModel):
    text: str
    language: str
    duration: float
    segments: list[Segment] = []


class HttpTranscriber:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 120.0,
        default_language: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._default_language = default_language

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        data: dict[str, str] = {}
        if self._default_language is not None:
            data["language"] = self._default_language

        with audio_path.open("rb") as handle:
            files = {"file": (audio_path.name, handle, "application/octet-stream")}
            response = httpx.post(
                f"{self._base_url}/transcribe",
                headers={"X-API-Key": self._api_key},
                files=files,
                data=data,
                timeout=self._timeout,
            )
        response.raise_for_status()
        return TranscriptionResult.model_validate(response.json())


transcriber = HttpTranscriber(
    "http://localhost:8000",
    api_key=os.environ["VOICE_RECOGNITION_API_KEY"],
    default_language="ru",
)
result = transcriber.transcribe(Path("audio.ogg"))
print(result.text)
```

### Адаптер `transcribe -> str`

Если потребитель ожидает старую сигнатуру (только текст без сегментов):

```python
from pathlib import Path
from typing import Protocol


class ITranscriber(Protocol):
    def transcribe(self, audio_path: Path) -> TranscriptionResult: ...


class TextTranscriberAdapter:
    def __init__(self, transcriber: ITranscriber) -> None:
        self._transcriber = transcriber

    def transcribe(self, audio_path: Path) -> str:
        return self._transcriber.transcribe(audio_path).text
```
