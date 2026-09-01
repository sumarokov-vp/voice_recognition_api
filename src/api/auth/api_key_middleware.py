import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from api.auth.api_key_registry import ApiKeyRegistry

API_KEY_HEADER = "X-API-Key"
OPEN_PATHS = frozenset({"/health"})

logger = logging.getLogger(__name__)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Пускает дальше только запрос с известным ключом и называет потребителя в логе.

    Проверка стоит на всём приложении, а не зависимостью на ручках: новая ручка
    тогда закрыта по умолчанию, а не по забывчивости автора. Открытых путей ровно
    столько, сколько перечислено в `open_paths` — по ним живёт healthcheck.
    """

    def __init__(
        self,
        app: ASGIApp,
        registry: ApiKeyRegistry,
        open_paths: frozenset[str] = OPEN_PATHS,
    ) -> None:
        super().__init__(app)
        self._registry = registry
        self._open_paths = open_paths

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if path in self._open_paths:
            return await call_next(request)

        presented_key = request.headers.get(API_KEY_HEADER)
        if presented_key is None:
            logger.warning("Отказ: запрос без ключа, %s %s", request.method, path)
            return self._unauthorized(f"Требуется заголовок {API_KEY_HEADER}")

        consumer = self._registry.consumer_for(presented_key)
        if consumer is None:
            logger.warning("Отказ: неизвестный ключ, %s %s", request.method, path)
            return self._unauthorized("Ключ неизвестен")

        request.state.consumer = consumer
        logger.info("Потребитель %s: %s %s", consumer, request.method, path)
        return await call_next(request)

    @staticmethod
    def _unauthorized(detail: str) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": detail})
