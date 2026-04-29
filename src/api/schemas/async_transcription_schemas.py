from pydantic import BaseModel

from api.schemas.transcription_response import TranscriptionResponse


class SubmitJobResponse(BaseModel):
    """Ответ на постановку задачи транскрипции (POST /transcribe/async)."""

    job_id: str


class JobStatusResponse(BaseModel):
    """Ответ на запрос статуса задачи транскрипции (GET /transcribe/async/{job_id})."""

    job_id: str
    status: str
    result: TranscriptionResponse | None = None
    error: str | None = None
