from pydantic import BaseModel

MLX_DEVICE = "metal"


class MlxWhisperEngineConfig(BaseModel):
    """Настройки движка mlx-whisper.

    Модель задаётся repo id на Hugging Face, а не путём к каталогу: у MLX
    своя раскладка весов, каталог моделей faster-whisper ему не подходит.
    Веса кешируются huggingface_hub в ~/.cache/huggingface.
    """

    model: str = "mlx-community/whisper-large-v3-turbo"
    language: str = "ru"

    @property
    def device(self) -> str:
        """У MLX выбора устройства нет: счёт всегда идёт на Apple GPU через Metal."""
        return MLX_DEVICE
