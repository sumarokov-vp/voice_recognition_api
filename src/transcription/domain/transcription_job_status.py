from enum import StrEnum


class TranscriptionJobStatus(StrEnum):
    """Жизненный цикл задачи транскрипции."""

    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
