from pydantic import BaseModel


class SegmentSchema(BaseModel):
    """Сериализационный DTO сегмента для HTTP-ответа."""

    start: float
    end: float
    text: str
