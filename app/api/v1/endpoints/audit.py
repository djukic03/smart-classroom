from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.dependencies import AuditServiceDep, require_admin
from app.models.audit_log import AuditAction, AuditEntityType
from app.schemas.audit import (
    DEFAULT_AUDIT_LIMIT,
    MAX_AUDIT_LIMIT,
    AuditLogPage,
    AuditLogRead,
)

router = APIRouter(tags=["audit"], dependencies=[Depends(require_admin)])

StartQuery = Annotated[datetime | None, Query(alias="from")]
EndQuery = Annotated[datetime | None, Query(alias="to")]


@router.get("", response_model=AuditLogPage)
async def list_audit_logs(
    service: AuditServiceDep,
    entity_type: AuditEntityType | None = None,
    entity_id: int | None = None,
    user_id: int | None = None,
    action: AuditAction | None = None,
    start: StartQuery = None,
    end: EndQuery = None,
    limit: Annotated[int, Query(ge=1, le=MAX_AUDIT_LIMIT)] = DEFAULT_AUDIT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogPage:
    rows = await service.history(
        entity_type, entity_id, user_id, action, start, end, limit, offset
    )
    total = await service.count(entity_type, entity_id, user_id, action, start, end)
    return AuditLogPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[AuditLogRead.model_validate(row) for row in rows],
    )
