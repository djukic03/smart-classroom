from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Smart Classroom"
    debug: bool
    database_url: str
    secret_key: SecretStr
    access_token_expire_minutes: int = 30
    token_touch_interval_seconds: int = 60
    default_device_name: str = "nepoznat uredjaj"
    measurement_aggregate_min_range_hours: int = 24
    login_ip_attempt_limit: int = 20
    login_ip_window_seconds: float = 300.0
    login_account_attempt_limit: int = 5
    login_account_window_seconds: float = 300.0
    register_attempt_limit: int = 5
    register_window_seconds: float = 3600.0
    cors_origins: list[str] = []
    log_level: str
    log_format: Literal["json", "console"] = "json"
    mqtt_username: str
    mqtt_password: SecretStr
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 8883
    mqtt_ca_file: str = "mosquitto/certs/ca.crt"
    mqtt_client_id: str = "smart-classroom-backend"
    mqtt_keepalive_seconds: int = 60
    mqtt_reconnect_seconds: float = 5.0
    mqtt_consumer_enabled: bool = True
    mqtt_hook_allowed_hosts: list[str] = ["mosquitto"]
    mqtt_config_queue_size: int = 1000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("secret_key")
    @classmethod
    def _reject_placeholder_secret(cls, v: SecretStr) -> SecretStr:
        marker = v.get_secret_value().lower()
        if "replace-with" in marker or "change-me" in marker:
            raise ValueError(
                "SECRET_KEY contains a placeholder value; generate one with `openssl rand -hex 32`"
            )
        return v


settings = Settings()
