from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from api.protocols.i_transcribe_use_case import ITranscribeUseCase
from api.routes.dependencies import get_max_file_size_bytes, get_transcribe_use_case
from api.routes.upload_temp_file import UploadTempFile
from api.schemas.segment_schema import SegmentSchema
from api.schemas.transcription_response import TranscriptionResponse

router = APIRouter()


@router.post("/transcribe", response_model=TranscriptionResponse)
def transcribe(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    use_case: ITranscribeUseCase = Depends(get_transcribe_use_case),
    max_size: int = Depends(get_max_file_size_bytes),
) -> TranscriptionResponse:
    payload = file.file.read()
    if len(payload) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Файл превышает лимит {max_size // (1024 * 1024)} МБ",
        )
    suffix = Path(file.filename or "audio.bin").suffix or ".bin"
    with UploadTempFile(suffix=suffix).write(payload) as audio_path:
        result = use_case.execute(audio_path=audio_path, language=language)
    return TranscriptionResponse(
        text=result.text,
        language=result.language,
        duration=result.duration,
        segments=[SegmentSchema(start=s.start, end=s.end, text=s.text) for s in result.segments],
    )
