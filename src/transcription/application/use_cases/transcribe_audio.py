from pathlib import Path

from transcription.application.protocols.i_whisper_engine import IWhisperEngine
from transcription.domain.transcription_result import TranscriptionResult


class TranscribeAudioUseCase:
    """Основной сценарий: распознать аудиофайл.

    Делегирует работу движку (через Protocol), ничего не знает про конкретную
    реализацию (faster-whisper, openai и т.п.).
    """

    def __init__(self, engine: IWhisperEngine, default_language: str) -> None:
        self._engine = engine
        self._default_language = default_language

    def execute(self, audio_path: Path, language: str | None = None) -> TranscriptionResult:
        resolved_language = language or self._default_language
        return self._engine.transcribe(audio_path, resolved_language)
