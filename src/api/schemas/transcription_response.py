from pydantic import BaseModel

from api.schemas.segment_schema import SegmentSchema


class TranscriptionResponse(BaseModel):
    """Ответ эндпойнта POST /transcribe."""

    text: str
    language: str
    duration: float
    segments: list[SegmentSchema]
