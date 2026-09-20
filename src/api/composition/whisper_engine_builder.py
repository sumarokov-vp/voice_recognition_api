import logging

from api.composition.api_config import ApiConfig
from api.composition.built_whisper_engine import BuiltWhisperEngine
from api.composition.whisper_engine_kind import WhisperEngineKind
from transcription.infrastructure.faster_whisper_engine import FasterWhisperEngine
from transcription.infrastructure.mlx_whisper_engine import MlxWhisperEngine
from transcription.infrastructure.mlx_whisper_engine_config import MlxWhisperEngineConfig
from transcription.infrastructure.mlx_whisper_module_loader import load_mlx_whisper_module
from transcription.infrastructure.whisper_engine_config import WhisperEngineConfig

_SETTINGS_BY_ENGINE: dict[WhisperEngineKind, frozenset[str]] = {
    WhisperEngineKind.FASTER: frozenset(
        {"whisper_model", "whisper_device", "whisper_compute_type", "whisper_model_dir"},
    ),
    WhisperEngineKind.MLX: frozenset({"whisper_mlx_model"}),
}

_logger = logging.getLogger(__name__)


def build_whisper_engine(config: ApiConfig) -> BuiltWhisperEngine:
    """Выбрать реализацию движка по WHISPER_ENGINE.

    Модель не грузится: preload остаётся заботой composition root.
    """
    _warn_about_foreign_settings(config)
    if config.whisper_engine is WhisperEngineKind.MLX:
        return _build_mlx_engine(config)
    return _build_faster_engine(config)


def _build_faster_engine(config: ApiConfig) -> BuiltWhisperEngine:
    engine_config = WhisperEngineConfig(
        model=config.whisper_model,
        device=config.whisper_device,
        compute_type=config.whisper_compute_type,
        language=config.whisper_language,
        model_dir=config.whisper_model_dir,
    )
    return BuiltWhisperEngine(
        engine=FasterWhisperEngine(engine_config),
        model=engine_config.model,
        device=engine_config.device,
        language=engine_config.language,
    )


def _build_mlx_engine(config: ApiConfig) -> BuiltWhisperEngine:
    engine_config = MlxWhisperEngineConfig(
        model=config.whisper_mlx_model,
        language=config.whisper_language,
    )
    return BuiltWhisperEngine(
        engine=MlxWhisperEngine(engine_config, module_loader=load_mlx_whisper_module),
        model=engine_config.model,
        device=engine_config.device,
        language=engine_config.language,
    )


def _warn_about_foreign_settings(config: ApiConfig) -> None:
    """Сказать про настройки чужого движка вслух, но не ронять старт.

    Молчать нельзя: WHISPER_COMPUTE_TYPE=float16 при движке mlx выглядит
    работающим и не работает. Падать тоже нельзя: один .env переживает
    переключение движка туда и обратно, и половина переменных в нём всегда
    будет от другого движка.
    """
    own_settings = _SETTINGS_BY_ENGINE[config.whisper_engine]
    foreign_settings = set().union(*_SETTINGS_BY_ENGINE.values()) - own_settings
    ignored = sorted(foreign_settings & config.model_fields_set)
    if not ignored:
        return
    _logger.warning(
        "Движок %s не использует переменные: %s — они проигнорированы",
        config.whisper_engine.value,
        ", ".join(name.upper() for name in ignored),
    )
