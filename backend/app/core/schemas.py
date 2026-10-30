from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NotificationChannel = Literal["serverchan", "pushplus"]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    uptime_seconds: int
    data_dir: str
    database: Literal["ok", "error"]


class SettingsResponse(BaseModel):
    poll_interval_minutes: int = 30
    checkout_interval_hours: int = 6
    close_to_tray: bool = True
    auto_start: bool = False
    notification_channel: NotificationChannel = "serverchan"
    history_retention_days: int = 0


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    poll_interval_minutes: int | None = Field(default=None, ge=10, le=180)
    checkout_interval_hours: int | None = Field(default=None, ge=4, le=12)
    close_to_tray: bool | None = None
    auto_start: bool | None = None
    notification_channel: NotificationChannel | None = None
    history_retention_days: int | None = Field(default=None, ge=0)
