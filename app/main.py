import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.endpoints import (
    anomaly,
    auth,
    classroom,
    device,
    device_config,
    health,
    measurement,
    mqtt,
    push_token,
    user,
)
from app.core.config import settings
from app.core.database import dispose_engine
from app.core.exceptions import (
    AlreadyExistsError,
    AuthenticationError,
    InvalidParameterError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
)
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware
from app.workers import anomaly_notifier, mqtt_gateway

configure_logging()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    tasks: list[asyncio.Task[None]] = []
    if settings.mqtt_consumer_enabled:
        tasks.append(asyncio.create_task(mqtt_gateway.run()))
    if settings.anomaly_notify_enabled:
        tasks.append(asyncio.create_task(anomaly_notifier.run()))

    yield

    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
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


@app.exception_handler(InvalidParameterError)
async def _invalid_parameter_handler(
    request: Request, exc: InvalidParameterError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": str(exc)},
    )


@app.exception_handler(RateLimitedError)
async def _rate_limited_handler(request: Request, exc: RateLimitedError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": str(exc)},
        headers={"Retry-After": str(exc.retry_after)},
    )


app.include_router(health.router, prefix="/health")
app.include_router(auth.router, prefix="/api/v1/auth")
app.include_router(classroom.router, prefix="/api/v1/classrooms")
app.include_router(device.router, prefix="/api/v1/devices")
app.include_router(device_config.router, prefix="/api/v1/devices/{device_id}/config")
app.include_router(
    measurement.router, prefix="/api/v1/classrooms/{classroom_id}/measurements"
)
app.include_router(
    anomaly.router, prefix="/api/v1/classrooms/{classroom_id}/anomalies"
)
app.include_router(push_token.router, prefix="/api/v1/me/push-tokens")
app.include_router(user.router, prefix="/api/v1/users")
app.include_router(mqtt.router, prefix="/api/v1/mqtt")
