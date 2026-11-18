from typing import Annotated

from fastapi import APIRouter, Depends, Request
from loguru import logger
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.scheduler import reschedule_job
from app.core.schemas import SettingsPatch, SettingsResponse
from app.core.settings_store import apply_settings, load_settings
from app.services.edge_bridge import edge_bridge
from app.services.notifications import is_notification_configured

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]


def _settings_response(data: dict) -> SettingsResponse:
    return SettingsResponse(
        **data,
        notification_configured=is_notification_configured(),
    )


@router.get("/settings", response_model=SettingsResponse)
def get_settings(db: DbSession) -> SettingsResponse:
    return _settings_response(load_settings(db))


@router.patch("/settings", response_model=SettingsResponse)
async def update_settings(
    patch: SettingsPatch,
    request: Request,
    db: DbSession,
) -> SettingsResponse:
    updates = {
        key: value
        for key, value in patch.model_dump(exclude_unset=True).items()
        if value is not None
    }
    data = apply_settings(db, updates)

    if "capture_browser" in updates:
        edge_bridge.set_browser(data["capture_browser"])

    if "poll_interval_minutes" in updates:
        scheduler = getattr(request.app.state, "scheduler", None)
        if scheduler is not None:
            try:
                reschedule_job(scheduler, int(updates["poll_interval_minutes"]))
            except Exception:
                logger.exception("Failed to reschedule polling job")

    return _settings_response(data)
