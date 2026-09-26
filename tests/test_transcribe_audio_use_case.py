from pathlib import Path

from transcription.application.use_cases.transcribe_audio import TranscribeAudioUseCase
from transcription.domain.segment import Segment
from transcription.domain.transcription_result import TranscriptionResult


class _FakeEngine:
    def __init__(self, result: TranscriptionResult) -> None:
        self._result = result
        self.last_language: str | None = None
        self.last_path: Path | None = None
        self.last_initial_prompt: str | None = None

    def preload(self) -> None: ...

    def is_loaded(self) -> bool:
        return True

    def transcribe(
        self,
        audio_path: Path,
        language: str,
        initial_prompt: str | None,
    ) -> TranscriptionResult:
        self.last_path = audio_path
        self.last_language = language
        self.last_initial_prompt = initial_prompt
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


GLOSSARY = "Добавь задачу в Todoist. В Todoist'е, из Todoist'а, с Todoist'ом."


def _empty_result() -> TranscriptionResult:
    return TranscriptionResult(text="", language="ru", duration=0.0, segments=[])


def test_uses_default_initial_prompt_when_request_has_none() -> None:
    engine = _FakeEngine(_empty_result())
    use_case = TranscribeAudioUseCase(
        engine=engine,
        default_language="ru",
        default_initial_prompt=GLOSSARY,
    )

    use_case.execute(audio_path=Path("/tmp/x.ogg"))

    assert engine.last_initial_prompt == GLOSSARY


def test_request_prompt_replaces_default_instead_of_appending() -> None:
    engine = _FakeEngine(_empty_result())
    use_case = TranscribeAudioUseCase(
        engine=engine,
        default_language="ru",
        default_initial_prompt=GLOSSARY,
    )

    use_case.execute(audio_path=Path("/tmp/x.ogg"), prompt="Kubernetes, кубер.")

    assert engine.last_initial_prompt == "Kubernetes, кубер."


def test_empty_request_prompt_falls_back_to_default() -> None:
    engine = _FakeEngine(_empty_result())
    use_case = TranscribeAudioUseCase(
        engine=engine,
        default_language="ru",
        default_initial_prompt=GLOSSARY,
    )

    use_case.execute(audio_path=Path("/tmp/x.ogg"), prompt="")

    assert engine.last_initial_prompt == GLOSSARY


def test_empty_default_prompt_means_no_prompt() -> None:
    engine = _FakeEngine(_empty_result())
    use_case = TranscribeAudioUseCase(
        engine=engine,
        default_language="ru",
        default_initial_prompt="",
    )

    use_case.execute(audio_path=Path("/tmp/x.ogg"), prompt="")

    assert engine.last_initial_prompt is None
