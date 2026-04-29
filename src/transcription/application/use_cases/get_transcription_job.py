from transcription.application.protocols.i_job_repository import IJobRepository
from transcription.domain.exceptions import JobNotFoundError
from transcription.domain.transcription_job import TranscriptionJob


class GetTranscriptionJobUseCase:
    """Возвращает задачу транскрипции по идентификатору."""

    def __init__(self, repository: IJobRepository) -> None:
        self._repository = repository

    def execute(self, job_id: str) -> TranscriptionJob:
        job = self._repository.get(job_id)
        if job is None:
            raise JobNotFoundError(f"Задача с идентификатором {job_id} не найдена")
        return job
