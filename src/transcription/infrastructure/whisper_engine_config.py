from pydantic import BaseModel


class WhisperEngineConfig(BaseModel):
    """Настройки движка faster-whisper."""

    model: str = "medium"
    device: str = "cuda"
    compute_type: str = "float16"
    language: str = "ru"
    model_dir: str = "/models"
