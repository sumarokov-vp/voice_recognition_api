from pathlib import Path
from typing import Protocol

from transcription.domain.transcription_result import TranscriptionResult


class IWhisperEngine(Protocol):
    """Контракт движка распознавания речи.

    Протокол объявлен на стороне потребителя (application-слой use case)
    и не зависит от конкретной реализации.
    """

    def preload(self) -> None:
        """Инициализировать модель в памяти."""
        ...

    def is_loaded(self) -> bool:
        """Признак готовности модели к инференсу."""
        ...

    def transcribe(self, audio_path: Path, language: str) -> TranscriptionResult:
        """Распознать аудиофайл и вернуть результат с сегментами."""
        ...
