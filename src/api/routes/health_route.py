from fastapi import APIRouter, Depends

from api.protocols.i_health_probe import IHealthProbe
from api.routes.dependencies import get_health_probe
from api.schemas.health_response import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(probe: IHealthProbe = Depends(get_health_probe)) -> HealthResponse:
    snapshot = probe.execute()
    return HealthResponse(
        status=snapshot.status,
        model=snapshot.model,
        device=snapshot.device,
        loaded=snapshot.loaded,
    )
