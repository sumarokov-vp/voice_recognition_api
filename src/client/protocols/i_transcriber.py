from pathlib import Path
from typing import Protocol

from client.dtos.transcription_result import TranscriptionResult


class ITranscriber(Protocol):
    """Контракт транскрайбера для потребителей SDK (боты и т.п.).

    Этот Protocol лежит в клиентском пакете, потому что именно потребитель
    диктует контракт. Реализация (HTTP) удовлетворяет его структурно.
    """

    def transcribe(self, audio_path: Path) -> TranscriptionResult: ...
