from pydantic import BaseModel, Field


class Segment(BaseModel):
    """Фрагмент распознанной речи с временными границами."""

    start: float = Field(ge=0.0, description="Начало сегмента в секундах")
    end: float = Field(ge=0.0, description="Конец сегмента в секундах")
    text: str = Field(description="Распознанный текст сегмента")
