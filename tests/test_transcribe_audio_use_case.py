from pathlib import Path

from transcription.application.use_cases.transcribe_audio import TranscribeAudioUseCase
from transcription.domain.segment import Segment
from transcription.domain.transcription_result import TranscriptionResult


class _FakeEngine:
    def __init__(self, result: TranscriptionResult) -> None:
        self._result = result
        self.last_language: str | None = None
        self.last_path: Path | None = None

    def preload(self) -> None: ...

    def is_loaded(self) -> bool:
        return True

    def transcribe(self, audio_path: Path, language: str) -> TranscriptionResult:
        self.last_path = audio_path
        self.last_language = language
        return self._result


def test_uses_default_language_when_not_provided() -> None:
    engine = _FakeEngine(
        TranscriptionResult(
            text="привет",
            language="ru",
            duration=1.0,
            segments=[Segment(start=0.0, end=1.0, text="привет")],
        ),
    )
    use_case = TranscribeAudioUseCase(engine=engine, default_language="ru")

    result = use_case.execute(audio_path=Path("/tmp/x.ogg"))

    assert engine.last_language == "ru"
    assert result.text == "привет"


def test_overrides_language_when_provided() -> None:
    engine = _FakeEngine(
        TranscriptionResult(text="hello", language="en", duration=1.0, segments=[]),
    )
    use_case = TranscribeAudioUseCase(engine=engine, default_language="ru")

    use_case.execute(audio_path=Path("/tmp/x.ogg"), language="en")

    assert engine.last_language == "en"
