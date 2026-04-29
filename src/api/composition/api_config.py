from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiConfig(BaseSettings):
    """Настройки HTTP-сервиса из переменных окружения."""

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    max_file_size_mb: int = 1000

    whisper_model: str = "medium"
    whisper_device: str = "cuda"
    whisper_compute_type: str = "float16"
    whisper_language: str = "ru"
    whisper_model_dir: str = "/models"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024
