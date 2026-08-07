from app.core.exceptions import AuthenticationError
from app.repositories.device_repo import DeviceRepository
from app.core.config import settings

from app.models.device import DeviceStatus

ENTITY = "MQTT"


class MQTTService:
    def __init__(self, device_repo: DeviceRepository) -> None:
        self._device_repo = device_repo
        
        
    async def authenticate(self, username: str, password: str) -> bool:
        if username == settings.mqtt_username:
            return password == settings.mqtt_password
        device = await self._device_repo.get_by_username(username)
        if device is None or device.status is not DeviceStatus.ACTIVE:
            return False
        return device.hashed_password == password
        
    
    async def check_acl(self, username: str, topic: str, access: int) -> bool:
        if username == settings.mqtt_username:
            return True
        device = await self._device_repo.get_by_username(username)
        if device is not None and device.status is DeviceStatus.ACTIVE:
            if topic == f"classrooms/{device.classroom_id}" and access == 2:
                return True
            if topic == f"devices/config/{device.username}" and access in [1, 4]:
                return True
        return False