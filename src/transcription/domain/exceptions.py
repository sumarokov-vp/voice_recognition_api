class TranscriptionError(Exception):
    """Базовое исключение контекста transcription."""


class AudioDecodingError(TranscriptionError):
    """Не удалось декодировать аудиофайл."""


class ModelNotLoadedError(TranscriptionError):
    """Запрос транскрипции до загрузки модели."""


class JobNotFoundError(TranscriptionError):
    """Задача транскрипции с указанным идентификатором не найдена."""
