import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.app_factory import create_app
from api.auth.api_key_registry import ApiKeyRegistry, ApiKeysFormatError
from api.composition.api_config import ApiConfig
from transcription.application.use_cases.health_probe import HealthStatus
from transcription.domain.segment import Segment
from transcription.domain.transcription_result import TranscriptionResult

KNOWN_KEY = "known-key-of-voice-input"
CONSUMER = "voice_input"
MIDDLEWARE_LOGGER = "api.auth.api_key_middleware"


class _FakeHealthProbe:
    def execute(self) -> HealthStatus:
        return HealthStatus(status="ok", model="medium", device="cuda", loaded=True)


class _FakeTranscribeUseCase:
    def execute(self, audio_path: Path, language: str | None = None) -> TranscriptionResult:
        return TranscriptionResult(
            text="привет",
            language=language or "ru",
            duration=1.0,
            segments=[Segment(start=0.0, end=1.0, text="привет")],
        )


def _make_client() -> TestClient:
    """Приложение без lifespan: композиция подставлена, faster-whisper не поднимается."""
    config = ApiConfig(api_keys=f"{CONSUMER}:{KNOWN_KEY}")
    app = create_app(config)
    app.state.composition = SimpleNamespace(
        config=config,
        transcribe_use_case=_FakeTranscribeUseCase(),
        health_probe=_FakeHealthProbe(),
    )
    return TestClient(app)


def _audio_files() -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("audio.ogg", b"fake-audio", "application/octet-stream")}


def test_request_without_key_is_rejected() -> None:
    response = _make_client().post("/transcribe", files=_audio_files())

    assert response.status_code == 401
    assert "detail" in response.json()


def test_request_with_unknown_key_is_rejected() -> None:
    response = _make_client().post(
        "/transcribe",
        files=_audio_files(),
        headers={"X-API-Key": "someone-elses-key"},
    )

    assert response.status_code == 401
    assert "detail" in response.json()


def test_health_is_open_without_key() -> None:
    response = _make_client().get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_known_key_passes() -> None:
    response = _make_client().post(
        "/transcribe",
        files=_audio_files(),
        headers={"X-API-Key": KNOWN_KEY},
    )

    assert response.status_code == 200
    assert response.json()["text"] == "привет"


def test_docs_are_closed_without_key() -> None:
    client = _make_client()

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 401


def test_log_names_consumer_and_never_shows_key(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIDDLEWARE_LOGGER):
        _make_client().post(
            "/transcribe",
            files=_audio_files(),
            headers={"X-API-Key": KNOWN_KEY},
        )

    messages = [record.getMessage() for record in caplog.records]
    assert any(CONSUMER in message and "/transcribe" in message for message in messages)
    assert all(KNOWN_KEY not in message for message in messages)


def test_log_of_refusal_never_shows_key(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=MIDDLEWARE_LOGGER):
        _make_client().post(
            "/transcribe",
            files=_audio_files(),
            headers={"X-API-Key": "someone-elses-key"},
        )

    messages = [record.getMessage() for record in caplog.records]
    assert messages
    assert all("someone-elses-key" not in message for message in messages)


def test_registry_reads_several_consumers() -> None:
    registry = ApiKeyRegistry.parse("voice_input:one, ecto_bot:two")

    assert registry.consumers == ("voice_input", "ecto_bot")
    assert registry.consumer_for("one") == "voice_input"
    assert registry.consumer_for("two") == "ecto_bot"
    assert registry.consumer_for("three") is None


def test_registry_survives_non_ascii_key() -> None:
    registry = ApiKeyRegistry.parse(f"{CONSUMER}:{KNOWN_KEY}")

    assert registry.consumer_for("ключ-с-кириллицей") is None


@pytest.mark.parametrize("raw", ["", "   ", ",", "voice_input", "voice_input:", ":key"])
def test_registry_rejects_broken_format(raw: str) -> None:
    with pytest.raises(ApiKeysFormatError):
        ApiKeyRegistry.parse(raw)


def test_registry_rejects_duplicate_consumer() -> None:
    with pytest.raises(ApiKeysFormatError):
        ApiKeyRegistry.parse("voice_input:one,voice_input:two")


def test_config_refuses_empty_api_keys() -> None:
    with pytest.raises(ValidationError):
        ApiConfig(api_keys="")
