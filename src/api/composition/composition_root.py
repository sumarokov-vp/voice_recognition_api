from api.composition.api_config import ApiConfig
from api.composition.composition import Composition
from transcription.application.use_cases.health_probe import HealthProbeUseCase
from transcription.application.use_cases.transcribe_audio import TranscribeAudioUseCase
from transcription.infrastructure.faster_whisper_engine import FasterWhisperEngine
from transcription.infrastructure.whisper_engine_config import WhisperEngineConfig


def build_composition(config: ApiConfig) -> Composition:
    """Собрать граф зависимостей и вернуть готовую композицию."""
    engine_config = WhisperEngineConfig(
        model=config.whisper_model,
        device=config.whisper_device,
        compute_type=config.whisper_compute_type,
        language=config.whisper_language,
        model_dir=config.whisper_model_dir,
    )
    engine = FasterWhisperEngine(engine_config)
    engine.preload()

    transcribe_use_case = TranscribeAudioUseCase(
        engine=engine,
        default_language=engine_config.language,
    )
    health_probe = HealthProbeUseCase(
        engine=engine,
        model=engine_config.model,
        device=engine_config.device,
    )

    return Composition(
        config=config,
        transcribe_use_case=transcribe_use_case,
        health_probe=health_probe,
    )
