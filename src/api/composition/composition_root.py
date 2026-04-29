from api.composition.api_config import ApiConfig
from api.composition.composition import Composition
from transcription.application.use_cases.get_transcription_job import GetTranscriptionJobUseCase
from transcription.application.use_cases.health_probe import HealthProbeUseCase
from transcription.application.use_cases.submit_transcription_job import (
    SubmitTranscriptionJobUseCase,
)
from transcription.application.use_cases.transcribe_audio import TranscribeAudioUseCase
from transcription.infrastructure.faster_whisper_engine import FasterWhisperEngine
from transcription.infrastructure.in_memory_job_repository import InMemoryJobRepository
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

    job_repository = InMemoryJobRepository()
    submit_job_use_case = SubmitTranscriptionJobUseCase(
        repository=job_repository,
        engine=engine,
    )
    get_job_use_case = GetTranscriptionJobUseCase(repository=job_repository)

    return Composition(
        config=config,
        transcribe_use_case=transcribe_use_case,
        health_probe=health_probe,
        job_repository=job_repository,
        submit_job_use_case=submit_job_use_case,
        get_job_use_case=get_job_use_case,
    )
