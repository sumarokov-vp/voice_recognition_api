from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from api.auth.api_key_registry import ApiKeyRegistry


class ApiConfig(BaseSettings):
    """Настройки HTTP-сервиса из переменных окружения."""

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    max_file_size_mb: int = 1000

    api_keys: str

    whisper_model: str = "medium"
    whisper_device: str = "cuda"
    whisper_compute_type: str = "float16"
    whisper_language: str = "ru"
    whisper_model_dir: str = "/models"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("api_keys")
    @classmethod
    def _check_api_keys(cls, value: str) -> str:
        """Формат разбирается сразу: кривой API_KEYS роняет старт, а не первый запрос."""
        ApiKeyRegistry.parse(value)
        return value

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def api_key_registry(self) -> ApiKeyRegistry:
        return ApiKeyRegistry.parse(self.api_keys)
