# Архитектура сервиса voice_recognition

Сервис локального распознавания голосовых сообщений на базе `faster-whisper`.
Поднимается в Docker, предоставляет HTTP API, к которому подключаются локальные
боты через тонкий клиентский SDK.

## Bounded contexts

Проект разбит на три независимых bounded context, каждый со своей зоной
ответственности и своим набором слоёв.

```
src/
|-- transcription/        # Ядро: доменная модель + use case транскрипции + движок
|-- api/                  # HTTP-слой: FastAPI-приложение, роуты, DI
`-- client/               # SDK для ботов: Protocol + httpx-реализация + DTO
```

Потребители сервиса (боты) подключают только пакет `src/client`. Внутри
сервиса — контексты `transcription` и `api`. Клиент полностью изолирован от
серверных зависимостей (`faster-whisper`, `fastapi`).

### Правила импортов

```
api            ---> transcription        (api использует use case из ядра)
transcription  ---X api                   (ядро ничего не знает про HTTP)
client         ---X transcription,api     (клиент полностью автономен)
transcription  ---X client                (ядро не знает про SDK)
```

Проверяется через `lint-imports` (конфигурация в `pyproject.toml`).

## Где лежат протоколы (Dependency Inversion)

Протокол всегда лежит на стороне клиента зависимости. Даже если сигнатура
дублирует реализацию — это осознанное решение: контракт диктует потребитель,
реализация его удовлетворяет.

| Протокол               | Где объявлен (потребитель)                                    | Реализация                                                  |
|------------------------|---------------------------------------------------------------|-------------------------------------------------------------|
| `IWhisperEngine`       | `transcription/application/protocols/i_whisper_engine.py`     | `transcription/infrastructure/faster_whisper_engine.py`, `.../mlx_whisper_engine.py` |
| `IMlxWhisperModule`    | `transcription/infrastructure/protocols/i_mlx_whisper_module.py` | пакет `mlx_whisper` (внешний, подключается по требованию)  |
| `ITranscribeUseCase`   | `api/protocols/i_transcribe_use_case.py`                      | `transcription/application/use_cases/transcribe_audio.py`   |
| `IHealthProbe`         | `api/protocols/i_health_probe.py`                             | `transcription/application/use_cases/health_probe.py`       |
| `ITranscriber`         | `client/protocols/i_transcriber.py`                           | `client/http_transcriber.py`                                |

Ключевой нюанс: `ITranscribeUseCase` и `IHealthProbe` лежат в `api`, потому
что именно `api` является их потребителем. `transcription` предоставляет
реализации, но не зависит от `api`.

## Контекст transcription

```
src/transcription/
|-- domain/
|   |-- segment.py                     # Segment (start, end, text)
|   `-- transcription_result.py        # TranscriptionResult (text, language, duration, segments)
|-- application/
|   |-- protocols/
|   |   `-- i_whisper_engine.py        # Protocol IWhisperEngine — контракт движка
|   `-- use_cases/
|       |-- transcribe_audio.py        # TranscribeAudioUseCase
|       `-- health_probe.py            # HealthProbeUseCase
`-- infrastructure/
    |-- protocols/
    |   `-- i_mlx_whisper_module.py    # Контракт mlx_whisper глазами движка
    |-- faster_whisper_engine.py       # Реализация IWhisperEngine на faster-whisper
    |-- whisper_engine_config.py       # Pydantic-модель настроек faster-движка
    |-- mlx_whisper_engine.py          # Реализация IWhisperEngine на mlx-whisper
    |-- mlx_whisper_engine_config.py   # Pydantic-модель настроек mlx-движка
    `-- mlx_whisper_module_loader.py   # Отложенный импорт mlx_whisper
```

Слой `domain` — чистые pydantic-модели без зависимостей. Слой `application` —
use case и Protocol-интерфейсы к внешним системам. Слой `infrastructure` —
адаптеры к `faster-whisper` и `mlx-whisper`, каждый из которых реализует
`IWhisperEngine`.

### Два движка

`faster-whisper` работает на CUDA и на CPU, `mlx-whisper` — на Apple Silicon
(Metal). Реализация выбирается на старте по `WHISPER_ENGINE`, дальше вся
система видит один и тот же `IWhisperEngine` и о выборе не знает: ни use case,
ни роуты, ни формат ответа не меняются.

У движков разные настройки (устройство и точность против HF repo id), поэтому
у каждого свой config-объект, а не один общий с полями «для кого-то». Настройки
чужого движка, заданные явно, не игнорируются молча и не роняют старт — про них
пишется warning в `whisper_engine_builder`.

Пакет `mlx_whisper` ставится только на macOS/arm64, поэтому `mlx_whisper_engine`
не импортирует его на уровне модуля: импорт делает `mlx_whisper_module_loader`
по требованию, а отсутствие пакета превращается в `EngineUnavailableError`.
Движок получает загрузчик через конструктор, так что в тестах подставляется
фейковый модуль.

### Подсказка-глоссарий (initial_prompt)

Подсказка — параметр запроса, а не свойство движка, поэтому её значение по умолчанию
(`WHISPER_INITIAL_PROMPT`) не лежит в config-объектах движков: composition root отдаёт
его прямо в `TranscribeAudioUseCase`. Выбор делает use case: `prompt` запроса, иначе
значение из конфига, иначе `None`; пустая строка приравнена к отсутствию. Подсказка
запроса заменяет конфиговую, а не склеивается с ней — у Whisper на неё около 224
токенов, и склейка молча съедала бы хвост. Движки получают уже разрешённое значение
третьим аргументом `IWhisperEngine.transcribe` и передают его в `initial_prompt` своей
библиотеки. Прогрев mlx-движка идёт без подсказки: на тишине она только провоцирует
модель повторить её в тексте.

## Контекст api

```
src/api/
|-- protocols/
|   |-- i_transcribe_use_case.py       # Контракт use case, который вызывает роут
|   `-- i_health_probe.py              # Контракт health-пробы
|-- schemas/
|   |-- transcription_response.py      # Pydantic-схема ответа POST /transcribe
|   |-- segment_schema.py              # Pydantic-схема сегмента
|   `-- health_response.py             # Pydantic-схема ответа GET /health
|-- routes/
|   |-- transcribe_route.py            # POST /transcribe
|   `-- health_route.py                # GET /health
|-- composition/
|   |-- api_config.py                  # Pydantic-settings для API (host, port, лимиты)
|   |-- whisper_engine_kind.py         # Enum faster | mlx — значение WHISPER_ENGINE
|   |-- whisper_engine_builder.py      # Выбор реализации движка по конфигу
|   |-- built_whisper_engine.py        # Движок + как он показывается в /health
|   `-- composition_root.py            # Сборка зависимостей, preload модели
`-- app_factory.py                     # create_app() -> FastAPI
```

`composition_root` — единственное место, где склеиваются реальные реализации
с протоколами. Роуты получают зависимости через `Depends`, которые отдают
готовые объекты из composition root.

## Контекст client (SDK)

```
src/client/
|-- protocols/
|   `-- i_transcriber.py               # Protocol ITranscriber — это импортируют боты
|-- dtos/
|   |-- transcription_result.py        # Результат транскрипции (совпадает с API)
|   `-- segment.py                     # Сегмент
|-- http_transcriber.py                # Реализация ITranscriber через httpx (возвращает TranscriptionResult)
|-- text_transcriber_adapter.py        # Адаптер: оборачивает HttpTranscriber и отдаёт только .text (str)
`-- http_transcriber_config.py         # Конфиг клиента (base_url, timeout)
```

Боты, которые мигрируют с `WhisperTranscriber` (возвращал `str`), используют
`TextTranscriberAdapter` — он оборачивает `HttpTranscriber` и даёт старую
сигнатуру `transcribe(audio_path) -> str`. Новые потребители могут работать
напрямую с `HttpTranscriber` и получать богатый `TranscriptionResult`.

Важно: DTO в `client` и domain-модели в `transcription` — это два разных
набора классов. Повторное использование между контекстами запрещено:
клиент не должен импортировать ничего из `transcription`.

## Composition root

Единственная точка, где собираются реальные реализации:

```python
# src/api/composition/composition_root.py

def build_composition(config: ApiConfig) -> Composition:
    built_engine = build_whisper_engine(config)   # faster или mlx — решает WHISPER_ENGINE
    engine = built_engine.engine
    engine.preload()
    transcribe_use_case = TranscribeAudioUseCase(
        engine,
        default_language=built_engine.language,
        default_initial_prompt=config.whisper_initial_prompt,
    )
    health_probe = HealthProbeUseCase(engine, model=built_engine.model, device=built_engine.device)
    return Composition(transcribe_use_case=transcribe_use_case, health_probe=health_probe, config=config)
```

`app_factory.create_app` вызывает `build_composition` в `lifespan` и кладёт
результат в `app.state`. Роуты через `Depends` достают use case из
`app.state`.

## Точки расширения

1. Замена движка — добавить новую реализацию `IWhisperEngine`, значение в
   `WhisperEngineKind` и ветку в `whisper_engine_builder` (так уже добавлен
   `MlxWhisperEngine`).
2. Добавить асинхронную очередь транскрипций — ввести новый use case
   `EnqueueTranscription`, который пишет в RabbitMQ, и отдельного воркера.
3. Диаризация (распознавание спикеров) — расширить `Segment` полем `speaker`
   и добавить отдельный use case, не трогая `TranscribeAudioUseCase`.

## Обработка ошибок

В соответствии с правилами проекта, классы не оборачивают свой код в
`try-except`. Исключения ловятся только на верхнем уровне:

- В `__main__.py` — для фатальных ошибок старта.
- В FastAPI — через exception handlers в `app_factory` (трансляция
  доменных исключений в HTTP-коды).

Доменные исключения определяются в `transcription/domain/exceptions.py`
(например, `AudioDecodingError`, `ModelNotLoadedError`,
`EngineUnavailableError`). Отсутствие пакета движка проверяется через
`importlib.util.find_spec`, а не через `try/except ImportError`.
