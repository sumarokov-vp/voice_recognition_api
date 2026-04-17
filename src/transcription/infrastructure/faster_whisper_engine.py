from pathlib import Path

from faster_whisper import WhisperModel

from transcription.domain.exceptions import ModelNotLoadedError
from transcription.domain.segment import Segment
from transcription.domain.transcription_result import TranscriptionResult
from transcription.infrastructure.whisper_engine_config import WhisperEngineConfig


class FasterWhisperEngine:
    """Реализация IWhisperEngine поверх faster-whisper.

    Намеренно не импортирует Protocol IWhisperEngine: связь structural,
    контракт проверяется mypy в composition root. Это соответствует правилу
    "Protocol на стороне клиента".
    """

    def __init__(self, config: WhisperEngineConfig) -> None:
        self._config = config
        self._model: WhisperModel | None = None

    def preload(self) -> None:
        self._model = WhisperModel(
            self._config.model,
            device=self._config.device,
            compute_type=self._config.compute_type,
            download_root=self._config.model_dir,
        )

    def is_loaded(self) -> bool:
        return self._model is not None

    def transcribe(self, audio_path: Path, language: str) -> TranscriptionResult:
        model = self._require_model()
        resolved_language = None if language == "auto" else language
        segments_iter, info = model.transcribe(
            str(audio_path),
            language=resolved_language,
            vad_filter=True,
        )
        segments = [
            Segment(start=float(s.start), end=float(s.end), text=s.text.strip())
            for s in segments_iter
        ]
        text = " ".join(segment.text for segment in segments if segment.text)
        return TranscriptionResult(
            text=text,
            language=info.language,
            duration=float(info.duration),
            segments=segments,
        )

    def _require_model(self) -> WhisperModel:
        if self._model is None:
            self.preload()
        if self._model is None:
            raise ModelNotLoadedError("Модель не была загружена")
        return self._model
