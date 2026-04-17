from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Ответ эндпойнта GET /health."""

    status: str
    model: str
    device: str
    loaded: bool
