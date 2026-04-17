from typing import Protocol

from transcription.application.use_cases.health_probe import HealthStatus


class IHealthProbe(Protocol):
    """Контракт пробы состояния для HTTP-роута."""

    def execute(self) -> HealthStatus: ...
