from pydantic import BaseModel, Field


class WhisperEngineConfig(BaseModel):
    """Настройки движка faster-whisper."""

    model: str = Field(default="small")
    device: str = Field(default="cpu")
    compute_type: str = Field(default="int8")
    language: str = Field(default="ru")
    model_dir: str = Field(default="/models")
