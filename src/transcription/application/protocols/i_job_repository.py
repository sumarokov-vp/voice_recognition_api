from typing import Protocol

from transcription.domain.transcription_job import TranscriptionJob


class IJobRepository(Protocol):
    """Контракт хранилища задач транскрипции.

    Объявлен на стороне потребителя (application use cases) и не зависит
    от конкретной реализации хранения (in-memory, Redis и т.п.).
    """

    def save(self, job: TranscriptionJob) -> None: ...

    def get(self, job_id: str) -> TranscriptionJob | None: ...

    def update(self, job: TranscriptionJob) -> None: ...
