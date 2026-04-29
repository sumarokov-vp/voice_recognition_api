from pathlib import Path
from typing import Protocol

from transcription.domain.transcription_job import TranscriptionJob


class ISubmitJobUseCase(Protocol):
    """Контракт постановки задачи транскрипции для HTTP-роута."""

    def submit(self, audio_path: Path, language: str | None = None) -> TranscriptionJob: ...
