from pydantic import BaseModel


class Segment(BaseModel):
    """Сегмент распознавания — клиентский DTO."""

    start: float
    end: float
    text: str
