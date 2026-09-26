from pathlib import Path

from transcription.application.protocols.i_whisper_engine import IWhisperEngine
from transcription.domain.transcription_result import TranscriptionResult


class TranscribeAudioUseCase:
    """Основной сценарий: распознать аудиофайл.

    Делегирует работу движку (через Protocol), ничего не знает про конкретную
    реализацию (faster-whisper, openai и т.п.).

    Подсказка из запроса заменяет подсказку из конфига целиком, а не дописывается
    к ней: у Whisper на initial_prompt около 224 токенов, склейка молча съедала бы
    хвост. Пустая строка значит «подсказки не передали».
    """

    def __init__(
        self,
        engine: IWhisperEngine,
        default_language: str,
        default_initial_prompt: str | None = None,
    ) -> None:
        self._engine = engine
        self._default_language = default_language
        self._default_initial_prompt = default_initial_prompt or None

    def execute(
        self,
        audio_path: Path,
        language: str | None = None,
        prompt: str | None = None,
    ) -> TranscriptionResult:
        resolved_language = language or self._default_language
        resolved_prompt = prompt or self._default_initial_prompt
        return self._engine.transcribe(audio_path, resolved_language, resolved_prompt)
