from pathlib import Path

import httpx
import respx

from client.http_transcriber import HttpTranscriber
from client.http_transcriber_config import HttpTranscriberConfig
from client.text_transcriber_adapter import TextTranscriberAdapter


def _make_audio_file(tmp_path: Path) -> Path:
    audio_path = tmp_path / "sample.ogg"
    audio_path.write_bytes(b"fake-ogg-bytes")
    return audio_path


@respx.mock
def test_http_transcriber_posts_multipart_and_parses_response(tmp_path: Path) -> None:
    route = respx.post("http://service/transcribe").mock(
        return_value=httpx.Response(
            200,
            json={
                "text": "привет мир",
                "language": "ru",
                "duration": 2.5,
                "segments": [{"start": 0.0, "end": 2.5, "text": "привет мир"}],
            },
        ),
    )
    transcriber = HttpTranscriber(
        HttpTranscriberConfig(base_url="http://service", default_language="ru"),
    )

    result = transcriber.transcribe(_make_audio_file(tmp_path))

    assert route.called
    assert result.text == "привет мир"
    assert result.language == "ru"
    assert result.duration == 2.5
    assert len(result.segments) == 1


@respx.mock
def test_text_transcriber_adapter_returns_only_text(tmp_path: Path) -> None:
    respx.post("http://service/transcribe").mock(
        return_value=httpx.Response(
            200,
            json={"text": "hello", "language": "en", "duration": 1.0, "segments": []},
        ),
    )
    adapter = TextTranscriberAdapter(
        HttpTranscriber(HttpTranscriberConfig(base_url="http://service")),
    )

    text = adapter.transcribe(_make_audio_file(tmp_path))

    assert text == "hello"
