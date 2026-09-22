import logging
from typing import Any

import pytest
from pydantic import ValidationError

from api.composition.api_config import ApiConfig
from api.composition.whisper_engine_builder import build_whisper_engine
from transcription.infrastructure.faster_whisper_engine import FasterWhisperEngine
from transcription.infrastructure.mlx_whisper_engine import MlxWhisperEngine

BUILDER_LOGGER = "api.composition.whisper_engine_builder"


def _make_config(**overrides: Any) -> ApiConfig:
    """Конфиг без чтения .env: тест не должен зависеть от машины разработчика."""
    return ApiConfig(_env_file=None, api_keys="voice_input:key", **overrides)


def test_default_config_keeps_faster_whisper() -> None:
    built = build_whisper_engine(_make_config())

    assert isinstance(built.engine, FasterWhisperEngine)
    assert built.model == "medium"
    assert built.device == "cuda"


def test_mlx_engine_is_chosen_by_env_value() -> None:
    built = build_whisper_engine(_make_config(whisper_engine="mlx"))

    assert isinstance(built.engine, MlxWhisperEngine)
    assert built.model == "mlx-community/whisper-large-v3-turbo"
    assert built.device == "metal"
    assert built.engine.is_loaded() is False


def test_mlx_model_is_taken_from_its_own_variable() -> None:
    built = build_whisper_engine(
        _make_config(whisper_engine="mlx", whisper_mlx_model="mlx-community/whisper-large-v3-mlx"),
    )

    assert built.model == "mlx-community/whisper-large-v3-mlx"


def test_settings_of_other_engine_are_reported_and_not_fatal(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger=BUILDER_LOGGER):
        built = build_whisper_engine(
            _make_config(whisper_engine="mlx", whisper_compute_type="float16"),
        )

    messages = [record.getMessage() for record in caplog.records]
    assert isinstance(built.engine, MlxWhisperEngine)
    assert any("WHISPER_COMPUTE_TYPE" in message for message in messages)


def test_untouched_settings_of_other_engine_stay_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger=BUILDER_LOGGER):
        build_whisper_engine(_make_config(whisper_engine="mlx"))

    assert caplog.records == []


def test_unknown_engine_name_breaks_startup() -> None:
    with pytest.raises(ValidationError):
        _make_config(whisper_engine="coreml")
