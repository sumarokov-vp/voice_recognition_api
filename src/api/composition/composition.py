from dataclasses import dataclass

from api.composition.api_config import ApiConfig
from api.protocols.i_get_job_use_case import IGetJobUseCase
from api.protocols.i_health_probe import IHealthProbe
from api.protocols.i_submit_job_use_case import ISubmitJobUseCase
from api.protocols.i_transcribe_use_case import ITranscribeUseCase
from transcription.application.protocols.i_job_repository import IJobRepository


@dataclass(frozen=True)
class Composition:
    """Контейнер собранных зависимостей для роутов."""

    config: ApiConfig
    transcribe_use_case: ITranscribeUseCase
    health_probe: IHealthProbe
    job_repository: IJobRepository
    submit_job_use_case: ISubmitJobUseCase
    get_job_use_case: IGetJobUseCase
