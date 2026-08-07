from fastapi import APIRouter

from app.api.v1.dependencies import MQTTServiceDep
from app.schemas.mqtt import MQTTAuthRequest, ACLRequest, SuperuserRequest, MQTTResponse


router = APIRouter(tags=["mqtt"])

@router.post("/auth", response_model=MQTTResponse)
async def auth(data: MQTTAuthRequest, service: MQTTServiceDep) -> MQTTResponse:
    allow = await service.authenticate(data.username, data.password)
    return MQTTResponse(ok=allow)

@router.post("/superuser", response_model=MQTTResponse)
async def superuser(data: SuperuserRequest, service: MQTTServiceDep) -> MQTTResponse:
    allow = await service.is_superuser(data.username)
    return MQTTResponse(ok=allow)

@router.post("/acl", response_model=MQTTResponse)
async def acl(data: ACLRequest, service: MQTTServiceDep) -> MQTTResponse:
    allow = await service.check_acl(data.username, data.topic, data.acc)
    return MQTTResponse(ok=allow)