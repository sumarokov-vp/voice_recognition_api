from transcription.application.protocols.i_whisper_engine import IWhisperEngine


class HealthStatus:
    """Снимок состояния движка для health-эндпойнта."""

    def __init__(self, *, status: str, model: str, device: str, loaded: bool) -> None:
        self.status = status
        self.model = model
        self.device = device
        self.loaded = loaded


class HealthProbeUseCase:
    """Возвращает состояние сервиса и загруженной модели."""

    def __init__(self, engine: IWhisperEngine, model: str, device: str) -> None:
        self._engine = engine
        self._model = model
        self._device = device

    def execute(self) -> HealthStatus:
        loaded = self._engine.is_loaded()
        return HealthStatus(
            status="ok" if loaded else "loading",
            model=self._model,
            device=self._device,
            loaded=loaded,
        )
