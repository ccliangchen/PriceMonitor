from fastapi import APIRouter, HTTPException
from loguru import logger

from app.core.schemas import NotificationConfigRequest, NotificationStatusResponse
from app.services.notifications import (
    clear_serverchan_key,
    is_notification_configured,
    send_test_notification,
    set_serverchan_key,
)

router = APIRouter()


def _status() -> NotificationStatusResponse:
    return NotificationStatusResponse(
        serverchan_configured=is_notification_configured()
    )


@router.get("/notifications/status", response_model=NotificationStatusResponse)
def notification_status() -> NotificationStatusResponse:
    return _status()


@router.put("/notifications/serverchan", response_model=NotificationStatusResponse)
def save_serverchan_key(payload: NotificationConfigRequest) -> NotificationStatusResponse:
    set_serverchan_key(payload.serverchan_sendkey)
    return _status()


@router.delete("/notifications/serverchan", response_model=NotificationStatusResponse)
def remove_serverchan_key() -> NotificationStatusResponse:
    clear_serverchan_key()
    return _status()


@router.post("/notifications/test")
async def test_notification() -> dict[str, bool]:
    try:
        await send_test_notification()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Test notification failed")
        raise HTTPException(status_code=502, detail=f"测试通知发送失败：{exc}") from exc
    return {"sent": True}
