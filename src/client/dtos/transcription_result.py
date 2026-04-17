from pydantic import BaseModel

from client.dtos.segment import Segment


class TranscriptionResult(BaseModel):
    """Результат транскрипции — клиентский DTO, совместим с ответом API."""

    text: str
    language: str
    duration: float
    segments: list[Segment] = []
