import asyncio
import tempfile
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)

from api.protocols.i_get_job_use_case import IGetJobUseCase
from api.protocols.i_submit_job_use_case import ISubmitJobUseCase
from api.protocols.i_transcribe_use_case import ITranscribeUseCase
from api.routes.dependencies import (
    get_get_job_use_case,
    get_job_repository,
    get_max_file_size_bytes,
    get_submit_job_use_case,
    get_transcribe_use_case,
)
from api.schemas.async_transcription_schemas import JobStatusResponse, SubmitJobResponse
from api.schemas.segment_schema import SegmentSchema
from api.schemas.transcription_response import TranscriptionResponse
from transcription.application.protocols.i_job_repository import IJobRepository
from transcription.domain.transcription_job import TranscriptionJob
from transcription.domain.transcription_job_status import TranscriptionJobStatus

router = APIRouter()


def _save_upload_to_temp(payload: bytes, suffix: str) -> Path:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(payload)
        handle.flush()
        return Path(handle.name)


def _delete_audio_file(audio_path: Path) -> None:
    if audio_path.exists():
        audio_path.unlink()


def _to_transcription_response(job: TranscriptionJob) -> TranscriptionResponse | None:
    if job.result is None:
        return None
    return TranscriptionResponse(
        text=job.result.text,
        language=job.result.language,
        duration=job.result.duration,
        segments=[
            SegmentSchema(start=s.start, end=s.end, text=s.text) for s in job.result.segments
        ],
    )


def _run_transcription_sync(
    job_id: str,
    language: str | None,
    repository: IJobRepository,
    transcribe_use_case: ITranscribeUseCase,
) -> None:
    job = repository.get(job_id)
    if job is None:
        return
    job.status = TranscriptionJobStatus.processing
    repository.update(job)
    try:
        result = transcribe_use_case.execute(audio_path=job.audio_path, language=language)
        job.result = result
        job.status = TranscriptionJobStatus.completed
    except Exception as exc:
        job.error = str(exc)
        job.status = TranscriptionJobStatus.failed
    finally:
        _delete_audio_file(job.audio_path)
        repository.update(job)


async def _run_transcription_in_thread(
    job_id: str,
    language: str | None,
    repository: IJobRepository,
    transcribe_use_case: ITranscribeUseCase,
) -> None:
    await asyncio.to_thread(
        _run_transcription_sync,
        job_id,
        language,
        repository,
        transcribe_use_case,
    )


@router.post(
    "/transcribe/async",
    response_model=SubmitJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_async_transcription(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    submit_use_case: ISubmitJobUseCase = Depends(get_submit_job_use_case),
    transcribe_use_case: ITranscribeUseCase = Depends(get_transcribe_use_case),
    repository: IJobRepository = Depends(get_job_repository),
    max_size: int = Depends(get_max_file_size_bytes),
) -> SubmitJobResponse:
    payload = await file.read()
    if len(payload) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Файл превышает лимит {max_size // (1024 * 1024)} МБ",
        )
    suffix = Path(file.filename or "audio.bin").suffix or ".bin"
    audio_path = _save_upload_to_temp(payload, suffix)
    job = submit_use_case.submit(audio_path=audio_path, language=language)
    background_tasks.add_task(
        _run_transcription_in_thread,
        job.id,
        language,
        repository,
        transcribe_use_case,
    )
    return SubmitJobResponse(job_id=job.id)


@router.get("/transcribe/async/{job_id}", response_model=JobStatusResponse)
def get_async_transcription_status(
    job_id: str,
    get_use_case: IGetJobUseCase = Depends(get_get_job_use_case),
) -> JobStatusResponse:
    job = get_use_case.execute(job_id)
    return JobStatusResponse(
        job_id=job.id,
        status=job.status.value,
        result=_to_transcription_response(job),
        error=job.error,
    )
