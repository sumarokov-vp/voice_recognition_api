from dataclasses import dataclass

from api.composition.api_config import ApiConfig
from api.protocols.i_health_probe import IHealthProbe
from api.protocols.i_transcribe_use_case import ITranscribeUseCase


@dataclass(frozen=True)
class Composition:
    """Контейнер собранных зависимостей для роутов."""

    config: ApiConfig
    transcribe_use_case: ITranscribeUseCase
    health_probe: IHealthProbe
