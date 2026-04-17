from pydantic import BaseModel, Field

from transcription.domain.segment import Segment


class TranscriptionResult(BaseModel):
    """Результат распознавания аудиофайла."""

    text: str = Field(description="Полный распознанный текст")
    language: str = Field(description="Код языка результата (например, ru)")
    duration: float = Field(ge=0.0, description="Длительность аудио в секундах")
    segments: list[Segment] = Field(default_factory=list)
