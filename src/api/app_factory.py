from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.composition.api_config import ApiConfig
from api.composition.composition_root import build_composition
from api.routes.async_transcribe_route import router as async_transcribe_router
from api.routes.health_route import router as health_router
from api.routes.transcribe_route import router as transcribe_router
from transcription.domain.exceptions import (
    AudioDecodingError,
    JobNotFoundError,
    ModelNotLoadedError,
    TranscriptionError,
)


def create_app(config: ApiConfig | None = None) -> FastAPI:
    """Собрать и вернуть FastAPI-приложение."""
    effective_config = config or ApiConfig()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.composition = build_composition(effective_config)
        yield

    app = FastAPI(title="voice_recognition", lifespan=lifespan)

    @app.exception_handler(AudioDecodingError)
    async def handle_audio_error(_: Request, exc: AudioDecodingError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(ModelNotLoadedError)
    async def handle_model_error(_: Request, exc: ModelNotLoadedError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(JobNotFoundError)
    async def handle_job_not_found(_: Request, exc: JobNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(TranscriptionError)
    async def handle_transcription_error(_: Request, exc: TranscriptionError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    app.include_router(health_router)
    app.include_router(transcribe_router)
    app.include_router(async_transcribe_router)

    return app
