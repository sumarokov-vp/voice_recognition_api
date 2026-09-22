import logging
import tempfile
import time
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

from transcription.domain.exceptions import ModelNotLoadedError
from transcription.domain.segment import Segment
from transcription.domain.transcription_result import TranscriptionResult
from transcription.infrastructure.mlx_whisper_engine_config import MlxWhisperEngineConfig
from transcription.infrastructure.protocols.i_mlx_whisper_module import IMlxWhisperModule

AUTO_LANGUAGE = "auto"
WARMUP_SAMPLE_RATE = 16000
WARMUP_SECONDS = 1


class MlxWhisperEngine:
    """Реализация IWhisperEngine поверх mlx-whisper (Apple Silicon).

    Намеренно не импортирует Protocol IWhisperEngine: связь structural,
    контракт проверяется mypy в composition root. Это соответствует правилу
    "Protocol на стороне клиента".

    Сам пакет mlx_whisper приходит через module_loader, а не импортом модуля:
    на Linux его нет, и импорт обязан оставаться безопасным.
    """

    def __init__(
        self,
        config: MlxWhisperEngineConfig,
        module_loader: Callable[[], IMlxWhisperModule],
    ) -> None:
        self._config = config
        self._module_loader = module_loader
        self._module: IMlxWhisperModule | None = None
        self._logger = logging.getLogger(__name__)

    def preload(self) -> None:
        """Подключить mlx_whisper и прогреть модель.

        mlx_whisper сам грузит веса лениво, внутри первого transcribe, и кеширует
        их у себя. Оставить это на первый пользовательский запрос нельзя: там
        скачивание модели с Hugging Face, и вызывающий бот успеет отвалиться по
        таймауту. Поэтому старт прогоняет через модель секунду тишины — после
        этого is_loaded() не врёт, а заодно на старте вскрывается отсутствие
        ffmpeg, без которого не читается ни один аудиофайл.
        """
        self._logger.info(
            "Загрузка модели mlx-whisper: model=%s device=%s",
            self._config.model,
            self._config.device,
        )
        module = self._module_loader()
        with tempfile.TemporaryDirectory() as directory:
            silence_path = Path(directory) / "silence.wav"
            self._write_silence(silence_path)
            module.transcribe(
                str(silence_path),
                path_or_hf_repo=self._config.model,
                language=self._resolve_language(self._config.language),
            )
        self._module = module
        self._logger.info("Модель mlx-whisper готова: model=%s", self._config.model)

    def is_loaded(self) -> bool:
        return self._module is not None

    def transcribe(self, audio_path: Path, language: str) -> TranscriptionResult:
        """Распознать файл.

        Длительность берётся по концу последнего сегмента: mlx_whisper, в отличие
        от faster-whisper, не отдаёт длину аудио отдельным полем, а декодировать
        файл второй раз ради одного числа дороже, чем погрешность на хвостовой
        тишине.
        """
        module = self._require_module()
        resolved_language = self._resolve_language(language)
        wall_start = time.monotonic()
        raw_result = module.transcribe(
            str(audio_path),
            path_or_hf_repo=self._config.model,
            language=resolved_language,
        )
        segments = self._read_segments(raw_result)
        audio_duration = segments[-1].end if segments else 0.0
        for segment in segments:
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
        return TranscriptionResult(
            text=self._read_text(raw_result, segments),
            language=str(raw_result.get("language") or resolved_language or language),
            duration=audio_duration,
            segments=segments,
        )

    @staticmethod
    def _resolve_language(language: str) -> str | None:
        """None означает для mlx_whisper автоопределение языка."""
        return None if language == AUTO_LANGUAGE else language

    @staticmethod
    def _write_silence(path: Path) -> None:
        with wave.open(str(path), "wb") as silence:
            silence.setnchannels(1)
            silence.setsampwidth(2)
            silence.setframerate(WARMUP_SAMPLE_RATE)
            silence.writeframes(b"\x00\x00" * (WARMUP_SAMPLE_RATE * WARMUP_SECONDS))

    @staticmethod
    def _read_segments(raw_result: dict[str, Any]) -> list[Segment]:
        raw_segments: list[dict[str, Any]] = raw_result.get("segments") or []
        return [
            Segment(
                start=float(raw_segment["start"]),
                end=float(raw_segment["end"]),
                text=str(raw_segment["text"]).strip(),
            )
            for raw_segment in raw_segments
        ]

    @staticmethod
    def _read_text(raw_result: dict[str, Any], segments: list[Segment]) -> str:
        """Текст собирается из сегментов — как у faster-whisper, чтобы ответ API не разъезжался.

        Верхнеуровневый text используется только когда сегментов нет вовсе.
        """
        if segments:
            return " ".join(segment.text for segment in segments if segment.text)
        return str(raw_result.get("text") or "").strip()

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        total_seconds = int(seconds)
        minutes = total_seconds // 60
        remaining_seconds = total_seconds % 60
        return f"{minutes:02d}:{remaining_seconds:02d}"

    def _require_module(self) -> IMlxWhisperModule:
        if self._module is None:
            self.preload()
        if self._module is None:
            raise ModelNotLoadedError("Движок mlx-whisper не был подключён")
        return self._module
