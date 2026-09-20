from enum import StrEnum


class WhisperEngineKind(StrEnum):
    """Какой реализацией IWhisperEngine поднимается сервис."""

    FASTER = "faster"
    MLX = "mlx"
