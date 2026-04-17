class TranscriptionError(Exception):
    """Базовое исключение контекста transcription."""


class AudioDecodingError(TranscriptionError):
    """Не удалось декодировать аудиофайл."""


class ModelNotLoadedError(TranscriptionError):
    """Запрос транскрипции до загрузки модели."""
