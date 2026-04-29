from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from transcription.domain.transcription_job_status import TranscriptionJobStatus
from transcription.domain.transcription_result import TranscriptionResult


@dataclass
class TranscriptionJob:
    """Задача асинхронной транскрипции."""

    id: str
    status: TranscriptionJobStatus
    audio_path: Path
    result: TranscriptionResult | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
