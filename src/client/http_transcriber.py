from pathlib import Path

import httpx

from client.dtos.transcription_result import TranscriptionResult
from client.http_transcriber_config import HttpTranscriberConfig


class HttpTranscriber:
    """HTTP-реализация ITranscriber: загружает файл и получает результат.

    Protocol ITranscriber лежит в client.protocols и не импортируется
    реализацией — связь structural.
    """

    def __init__(self, config: HttpTranscriberConfig) -> None:
        self._config = config

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        data: dict[str, str] = {}
        if self._config.default_language is not None:
            data["language"] = self._config.default_language

        with audio_path.open("rb") as handle:
            files = {"file": (audio_path.name, handle, "application/octet-stream")}
            response = httpx.post(
                self._endpoint(),
                files=files,
                data=data,
                timeout=self._config.timeout_seconds,
            )
        response.raise_for_status()
        return TranscriptionResult.model_validate(response.json())

    def _endpoint(self) -> str:
        return f"{self._config.base_url.rstrip('/')}/transcribe"
