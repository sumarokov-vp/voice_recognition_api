import importlib.util
import wave
from pathlib import Path
from typing import Any

import pytest

from transcription.domain.exceptions import EngineUnavailableError
from transcription.infrastructure.mlx_whisper_engine import MlxWhisperEngine
from transcription.infrastructure.mlx_whisper_engine_config import MlxWhisperEngineConfig
from transcription.infrastructure.mlx_whisper_module_loader import load_mlx_whisper_module

AUDIO_PATH = Path("/tmp/voice.ogg")


def _probe_wav(path: str) -> tuple[int, int] | None:
    """Частота и число фреймов; читается в момент вызова — временный файл потом исчезнет."""
    if not Path(path).is_file():
        return None
    with wave.open(path, "rb") as audio:
        return audio.getframerate(), audio.getnframes()


class _FakeMlxWhisperModule:
    def __init__(self, result: dict[str, Any]) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []
        self.probes: list[tuple[int, int] | None] = []

    def transcribe(
        self,
        audio: str,
        *,
        path_or_hf_repo: str,
        language: str | None,
        initial_prompt: str | None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "audio": audio,
                "path_or_hf_repo": path_or_hf_repo,
                "language": language,
                "initial_prompt": initial_prompt,
            },
        )
        self.probes.append(_probe_wav(audio))
        return self._result


class _CountingLoader:
    def __init__(self, module: _FakeMlxWhisperModule) -> None:
        self._module = module
        self.load_count = 0

    def __call__(self) -> _FakeMlxWhisperModule:
        self.load_count += 1
        return self._module


def _make_engine(
    result: dict[str, Any],
    model: str = "mlx-community/whisper-large-v3-turbo",
    language: str = "ru",
) -> tuple[MlxWhisperEngine, _FakeMlxWhisperModule, _CountingLoader]:
    module = _FakeMlxWhisperModule(result)
    loader = _CountingLoader(module)
    config = MlxWhisperEngineConfig(model=model, language=language)
    return MlxWhisperEngine(config, module_loader=loader), module, loader


def _result_with_two_segments() -> dict[str, Any]:
    return {
        "text": " привет мир ",
        "language": "ru",
        "segments": [
            {"seek": 0, "start": 0.0, "end": 1.5, "text": " привет", "no_speech_prob": 0.1},
            {"seek": 0, "start": 1.5, "end": 4.25, "text": " мир ", "no_speech_prob": 0.1},
        ],
    }


def test_maps_mlx_result_to_domain_result() -> None:
    engine, _, _ = _make_engine(_result_with_two_segments())

    result = engine.transcribe(AUDIO_PATH, "ru", None)

    assert result.text == "привет мир"
    assert result.language == "ru"
    assert result.duration == 4.25
    assert [(segment.start, segment.end, segment.text) for segment in result.segments] == [
        (0.0, 1.5, "привет"),
        (1.5, 4.25, "мир"),
    ]


def test_model_goes_to_mlx_as_hf_repo() -> None:
    engine, module, _ = _make_engine(_result_with_two_segments(), model="mlx-community/other")

    engine.transcribe(AUDIO_PATH, "ru", None)

    assert module.calls[-1] == {
        "audio": str(AUDIO_PATH),
        "path_or_hf_repo": "mlx-community/other",
        "language": "ru",
        "initial_prompt": None,
    }


def test_auto_language_is_passed_as_none_and_detected_one_returned() -> None:
    result_payload = _result_with_two_segments()
    result_payload["language"] = "en"
    engine, module, _ = _make_engine(result_payload)

    result = engine.transcribe(AUDIO_PATH, "auto", None)

    assert module.calls[-1]["language"] is None
    assert result.language == "en"


def test_result_without_segments_falls_back_to_plain_text() -> None:
    engine, _, _ = _make_engine({"text": " привет ", "language": "ru", "segments": []})

    result = engine.transcribe(AUDIO_PATH, "ru", None)

    assert result.text == "привет"
    assert result.segments == []
    assert result.duration == 0.0


def test_preload_warms_model_up_on_a_second_of_silence() -> None:
    engine, module, _ = _make_engine(_result_with_two_segments())

    engine.preload()

    assert engine.is_loaded() is True
    assert module.probes == [(16000, 16000)]
    assert module.calls[0]["language"] == "ru"
    assert module.calls[0]["initial_prompt"] is None


def test_initial_prompt_goes_to_mlx_but_not_to_warm_up() -> None:
    engine, module, _ = _make_engine(_result_with_two_segments())

    engine.transcribe(AUDIO_PATH, "ru", "Todoist, в Todoist'е")

    assert [call["initial_prompt"] for call in module.calls] == [None, "Todoist, в Todoist'е"]


def test_module_is_loaded_lazily_and_only_once() -> None:
    engine, _, loader = _make_engine(_result_with_two_segments())

    assert engine.is_loaded() is False

    engine.transcribe(AUDIO_PATH, "ru", None)
    engine.transcribe(AUDIO_PATH, "ru", None)

    assert engine.is_loaded() is True
    assert loader.load_count == 1


def test_loader_explains_missing_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)

    with pytest.raises(EngineUnavailableError, match="mlx-whisper"):
        load_mlx_whisper_module()
