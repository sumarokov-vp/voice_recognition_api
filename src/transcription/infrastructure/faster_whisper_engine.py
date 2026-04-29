import logging
import time
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
        self._logger = logging.getLogger(__name__)

    def preload(self) -> None:
        self._logger.info(
            "Загрузка модели faster-whisper: model=%s device=%s compute_type=%s",
            self._config.model,
            self._config.device,
            self._config.compute_type,
        )
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
        wall_start = time.monotonic()
        segments_iter, info = model.transcribe(
            str(audio_path),
            language=resolved_language,
            vad_filter=True,
        )
        audio_duration = float(info.duration)
        segments: list[Segment] = []
        for raw_segment in segments_iter:
            segment = Segment(
                start=float(raw_segment.start),
                end=float(raw_segment.end),
                text=raw_segment.text.strip(),
            )
            segments.append(segment)
            progress = segment.end / audio_duration * 100 if audio_duration > 0 else 0
            self._logger.info(
                "[%s -> %s | %d%%] %s",
                self._format_timestamp(segment.start),
                self._format_timestamp(segment.end),
                int(progress),
                segment.text,
            )
        wall_time = time.monotonic() - wall_start
        time_factor = audio_duration / wall_time if wall_time > 0 else 0
        self._logger.info(
            "Распознавание завершено: wall_time=%.2fs audio_duration=%.2fs time_factor=%.2fx",
            wall_time,
            audio_duration,
            time_factor,
        )
        text = " ".join(segment.text for segment in segments if segment.text)
        return TranscriptionResult(
            text=text,
            language=info.language,
            duration=audio_duration,
            segments=segments,
        )

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        total_seconds = int(seconds)
        minutes = total_seconds // 60
        remaining_seconds = total_seconds % 60
        return f"{minutes:02d}:{remaining_seconds:02d}"

    def _require_model(self) -> WhisperModel:
        if self._model is None:
            self.preload()
        if self._model is None:
            raise ModelNotLoadedError("Модель не была загружена")
        return self._model
