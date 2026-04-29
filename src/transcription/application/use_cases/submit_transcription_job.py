import uuid
from pathlib import Path

from transcription.application.protocols.i_job_repository import IJobRepository
from transcription.application.protocols.i_whisper_engine import IWhisperEngine
from transcription.domain.transcription_job import TranscriptionJob
from transcription.domain.transcription_job_status import TranscriptionJobStatus


class SubmitTranscriptionJobUseCase:
    """Создаёт задачу транскрипции в статусе pending и сохраняет её в репозитории.

    Engine инжектится для будущего использования (например, проверки готовности
    модели), но запуск транскрипции — ответственность вызывающей стороны
    (API-слой запускает её в фоне).
    """

    def __init__(self, repository: IJobRepository, engine: IWhisperEngine) -> None:
        self._repository = repository
        self._engine = engine

    def submit(self, audio_path: Path, language: str | None = None) -> TranscriptionJob:
        job = TranscriptionJob(
            id=str(uuid.uuid4()),
            status=TranscriptionJobStatus.pending,
            audio_path=audio_path,
        )
        self._repository.save(job)
        return job
