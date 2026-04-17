from pathlib import Path
from typing import Protocol

from transcription.domain.transcription_result import TranscriptionResult


class ITranscribeUseCase(Protocol):
    """Контракт сценария транскрипции для HTTP-роута."""

    def execute(self, audio_path: Path, language: str | None = None) -> TranscriptionResult: ...
