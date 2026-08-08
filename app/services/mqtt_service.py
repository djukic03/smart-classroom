import secrets

from pwdlib.exceptions import UnknownHashError

from app.core.config import settings
from app.core.security import verify_password
from app.models.device import DeviceStatus
from app.repositories.device_repo import DeviceRepository
from app.utils.topics import config_topic, measurement_topic

ENTITY = "MQTT"

ACL_READ = 1
ACL_WRITE = 2
ACL_SUBSCRIBE = 4


class MQTTService:
    def __init__(self, device_repo: DeviceRepository) -> None:
        self._device_repo = device_repo

    async def authenticate(self, username: str, password: str) -> bool:
        if username == settings.mqtt_username:
            return secrets.compare_digest(
                password, settings.mqtt_password.get_secret_value()
            )

        device = await self._device_repo.get_by_username(username)
        if device is None or device.status is not DeviceStatus.ACTIVE:
            return False

        try:
            valid = verify_password(password, device.hashed_password)
        except UnknownHashError:
            return False

        if not valid:
            return False

        await self._device_repo.mark_seen(device)
        return True


    async def check_acl(self, username: str, topic: str, access: int) -> bool:
        if username == settings.mqtt_username:
            return True

        device = await self._device_repo.get_by_username(username)
        if device is None or device.status is not DeviceStatus.ACTIVE:
            return False

        if topic == measurement_topic(device.classroom_id, device.username):
            return access == ACL_WRITE
        if topic == config_topic(device.username):
            return access in (ACL_READ, ACL_SUBSCRIBE)
        return False
