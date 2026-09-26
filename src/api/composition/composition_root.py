from api.composition.api_config import ApiConfig
from api.composition.composition import Composition
from api.composition.whisper_engine_builder import build_whisper_engine
from transcription.application.use_cases.get_transcription_job import GetTranscriptionJobUseCase
from transcription.application.use_cases.health_probe import HealthProbeUseCase
from transcription.application.use_cases.submit_transcription_job import (
    SubmitTranscriptionJobUseCase,
)
from transcription.application.use_cases.transcribe_audio import TranscribeAudioUseCase
from transcription.infrastructure.in_memory_job_repository import InMemoryJobRepository


def build_composition(config: ApiConfig) -> Composition:
    """Собрать граф зависимостей и вернуть готовую композицию."""
    built_engine = build_whisper_engine(config)
    engine = built_engine.engine
    engine.preload()

    transcribe_use_case = TranscribeAudioUseCase(
        engine=engine,
        default_language=built_engine.language,
        default_initial_prompt=config.whisper_initial_prompt,
    )
    health_probe = HealthProbeUseCase(
        engine=engine,
        model=built_engine.model,
        device=built_engine.device,
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
