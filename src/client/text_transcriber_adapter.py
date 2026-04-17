from pathlib import Path

from client.protocols.i_transcriber import ITranscriber


class TextTranscriberAdapter:
    """Адаптер для обратной совместимости.

    Оборачивает любой ITranscriber и возвращает только строку с текстом —
    сигнатура, которую исторически ожидают боты (transcribe -> str).
    """

    def __init__(self, transcriber: ITranscriber) -> None:
        self._transcriber = transcriber

    def transcribe(self, audio_path: Path) -> str:
        result = self._transcriber.transcribe(audio_path)
        return result.text
