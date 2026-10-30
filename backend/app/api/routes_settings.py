from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import Setting, utcnow
from app.core.schemas import SettingsPatch, SettingsResponse

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]

DEFAULT_SETTINGS: dict[str, object] = {
    "poll_interval_minutes": 30,
    "checkout_interval_hours": 6,
    "close_to_tray": True,
    "auto_start": False,
    "notification_channel": "serverchan",
    "history_retention_days": 0,
}


def load_settings(db: Session) -> dict[str, object]:
    data = DEFAULT_SETTINGS.copy()
    for row in db.query(Setting).all():
        if row.key in data:
            data[row.key] = row.value
    return data


@router.get("/settings", response_model=SettingsResponse)
def get_settings(db: DbSession) -> SettingsResponse:
    return SettingsResponse(**load_settings(db))


@router.patch("/settings", response_model=SettingsResponse)
def update_settings(
    patch: SettingsPatch,
    db: DbSession,
) -> SettingsResponse:
    updates = {
        key: value
        for key, value in patch.model_dump(exclude_unset=True).items()
        if value is not None
    }
    for key, value in updates.items():
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=value))
        else:
            row.value = value
            row.updated_at = utcnow()
    db.commit()
    return SettingsResponse(**load_settings(db))
