from typing import Protocol

from transcription.domain.transcription_job import TranscriptionJob


class IGetJobUseCase(Protocol):
    """Контракт получения статуса задачи транскрипции для HTTP-роута."""

    def execute(self, job_id: str) -> TranscriptionJob: ...
