import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATA_DIR = Path("D:/PriceMonitorData")


def default_data_dir() -> Path:
    env_dir = os.environ.get("PRICE_MONITOR_DATA_DIR")
    if env_dir:
        return Path(env_dir)
    if Path("D:/").exists():
        return DEFAULT_DATA_DIR
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "PriceMonitor"
    return Path.home() / ".price-monitor"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PRICE_MONITOR_",
        env_file=".env",
        extra="ignore",
    )

    port: int = 8765
    data_dir: Path = Field(default_factory=default_data_dir)
    token: str = ""
    log_level: str = "INFO"
    enable_scheduler: bool = True

    @property
    def db_path(self) -> Path:
        return self.data_dir / "data.db"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def browser_profiles_dir(self) -> Path:
        return self.data_dir / "browser_profiles"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"
