from pydantic import BaseModel, Field


class HttpTranscriberConfig(BaseModel):
    """Настройки HTTP-клиента транскрибера."""

    base_url: str = Field(description="Базовый URL сервиса voice_recognition")
    timeout_seconds: float = Field(default=120.0, ge=1.0)
    default_language: str | None = Field(default=None)
