from typing import Any

from sqlalchemy.orm import Session

from app.core.models import Setting, utcnow

DEFAULT_SETTINGS: dict[str, Any] = {
    "poll_interval_minutes": 30,
    "checkout_interval_hours": 6,
    "close_to_tray": True,
    "auto_start": False,
    "notification_channel": "serverchan",
    "history_retention_days": 0,
}


def load_settings(db: Session) -> dict[str, Any]:
    data = DEFAULT_SETTINGS.copy()
    for row in db.query(Setting).all():
        if row.key in data:
            data[row.key] = row.value
    return data


def apply_settings(db: Session, updates: dict[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=value))
        else:
            row.value = value
            row.updated_at = utcnow()
    db.commit()
    return load_settings(db)
