from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.mqtt import broker_state

router = APIRouter(tags=["health"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(db: DbSession) -> JSONResponse:
    checks: dict[str, str] = {}

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"unavailable: {type(exc).__name__}"

    if settings.mqtt_consumer_enabled:
        if broker_state.connected:
            checks["broker"] = "ok"
        else:
            checks["broker"] = f"disconnected: {broker_state.last_error or 'nema veze'}"
    else:
        checks["broker"] = "disabled"

    healthy = all(value in ("ok", "disabled") for value in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ready" if healthy else "not ready", **checks},
    )
