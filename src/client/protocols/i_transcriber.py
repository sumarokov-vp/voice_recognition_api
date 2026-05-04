from pathlib import Path
from typing import Protocol

from client.dtos.transcription_result import TranscriptionResult


class ITranscriber(Protocol):
    """Контракт транскрайбера для потребителей пакета (боты и т.п.).

    Этот Protocol лежит в клиентском пакете, потому что именно потребитель
    диктует контракт. Готовой реализации в пакете нет — пример HTTP-клиента
    смотри в README.
    """

    def transcribe(self, audio_path: Path) -> TranscriptionResult: ...
