from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.audit_log import AuditAction, AuditEntityType

MAX_AUDIT_LIMIT = 200
DEFAULT_AUDIT_LIMIT = 50


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    actor_email: str | None
    action: AuditAction
    entity_type: AuditEntityType
    entity_id: int | None
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    description: str | None
    timestamp: datetime


class AuditLogPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AuditLogRead]
