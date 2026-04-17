from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiConfig(BaseSettings):
    """Настройки HTTP-сервиса из переменных окружения."""

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    max_file_size_mb: int = 25

    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str = "ru"
    whisper_model_dir: str = "/models"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024
