import structlog
from fastapi import APIRouter, Depends, Request

from app.api.v1.dependencies import MQTTServiceDep, require_mqtt_hook_client
from app.schemas.mqtt import ACLRequest, MQTTAuthRequest, MQTTResponse

router = APIRouter(tags=["mqtt"], dependencies=[Depends(require_mqtt_hook_client)])

logger = structlog.get_logger("app.mqtt")


@router.post("/auth", response_model=MQTTResponse)
async def auth(
    data: MQTTAuthRequest, service: MQTTServiceDep, request: Request
) -> MQTTResponse:
    allow = await service.authenticate(data.username, data.password)
    if not allow:
        logger.warning(
            "mqtt_auth_denied",
            username=data.username,
            client=request.client.host if request.client else None,
        )
    return MQTTResponse(ok=allow)


@router.post("/acl", response_model=MQTTResponse)
async def acl(
    data: ACLRequest, service: MQTTServiceDep, request: Request
) -> MQTTResponse:
    allow = await service.check_acl(data.username, data.topic, data.acc)
    if not allow:
        logger.warning(
            "mqtt_acl_denied",
            username=data.username,
            topic=data.topic,
            acc=data.acc,
            client=request.client.host if request.client else None,
        )
    return MQTTResponse(ok=allow)
