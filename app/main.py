import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.endpoints import auth, classroom, health, mqtt
from app.core.config import settings
from app.core.database import dispose_engine
from app.core.exceptions import (
    AlreadyExistsError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware
from app.workers import measurement_consumer

configure_logging()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    consumer: asyncio.Task[None] | None = None
    if settings.mqtt_consumer_enabled:
        consumer = asyncio.create_task(measurement_consumer.run())

    yield

    if consumer is not None:
        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)
    await dispose_engine()

app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(NotFoundError)
async def _not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)}
    )


@app.exception_handler(AlreadyExistsError)
async def _already_exists_handler(request: Request, exc: AlreadyExistsError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc)}
    )


@app.exception_handler(AuthenticationError)
async def _authentication_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": str(exc)},
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.exception_handler(PermissionDeniedError)
async def _permission_denied_handler(request: Request, exc: PermissionDeniedError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": str(exc)}
    )


app.include_router(health.router, prefix="/health")
app.include_router(auth.router, prefix="/api/v1/auth")
app.include_router(classroom.router, prefix="/api/v1/classrooms")
app.include_router(mqtt.router, prefix="/api/v1/mqtt")
