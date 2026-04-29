import threading

from transcription.application.protocols.i_job_repository import IJobRepository
from transcription.domain.transcription_job import TranscriptionJob


class InMemoryJobRepository(IJobRepository):
    """Потокобезопасное in-memory хранилище задач транскрипции.

    При рестарте сервиса задачи теряются — это допустимо для текущих требований.
    Блокировка нужна, потому что запись и чтение идут из разных потоков
    (фоновая транскрипция выполняется в thread pool executor).
    """

    def __init__(self) -> None:
        self._jobs: dict[str, TranscriptionJob] = {}
        self._lock = threading.Lock()

    def save(self, job: TranscriptionJob) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def get(self, job_id: str) -> TranscriptionJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job: TranscriptionJob) -> None:
        with self._lock:
            self._jobs[job.id] = job
