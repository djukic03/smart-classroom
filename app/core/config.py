from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    password_reset_token_expire_minutes: int = 30
    password_reset_ip_attempt_limit: int = 5
    password_reset_ip_window_seconds: float = 3600.0
    password_reset_account_attempt_limit: int = 3
    password_reset_account_window_seconds: float = 3600.0
    frontend_reset_url: str = "http://localhost:3000/reset-password"
    mail_backend: Literal["console", "smtp"] = "console"
    mail_from: str = "no-reply@smart-classroom.local"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_starttls: bool = True
    schedule_timezone: str = "Europe/Belgrade"

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

    @field_validator("schedule_timezone")
    @classmethod
    def _known_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"SCHEDULE_TIMEZONE '{v}' nije poznata vremenska zona") from exc
        return v


settings = Settings()
