from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import Account
from app.core.schemas import AccountResponse, LoginStartedResponse
from app.services.accounts import (
    check_account,
    ensure_jd_account,
    logout_account,
    reconcile_stale_logins,
    start_login,
)

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]


def _ensure_platform(platform: str) -> None:
    if platform != "jd":
        raise HTTPException(status_code=404, detail="第一版只支持京东账号")


@router.get("/accounts", response_model=list[AccountResponse])
def list_accounts(request: Request, db: DbSession) -> list[AccountResponse]:
    ensure_jd_account(db, request.app.state.settings)
    reconcile_stale_logins(db)
    accounts = db.scalars(select(Account).order_by(Account.id)).all()
    return [AccountResponse.model_validate(item) for item in accounts]


@router.post("/accounts/{platform}/login", response_model=LoginStartedResponse)
async def login(platform: str, request: Request, db: DbSession) -> LoginStartedResponse:
    _ensure_platform(platform)
    account = ensure_jd_account(db, request.app.state.settings)
    started = start_login(account.id)
    return LoginStartedResponse(
        started=started,
        message=(
            "已打开京东登录窗口，请扫码完成登录"
            if started
            else "登录窗口已经在运行，请完成扫码"
        ),
    )


@router.post("/accounts/{platform}/logout", response_model=AccountResponse)
async def logout(platform: str, request: Request, db: DbSession) -> AccountResponse:
    _ensure_platform(platform)
    account = ensure_jd_account(db, request.app.state.settings)
    await logout_account(account.id, request.app.state.browser)
    db.refresh(account)
    return AccountResponse.model_validate(account)


@router.post("/accounts/{platform}/check", response_model=AccountResponse)
async def check(platform: str, request: Request, db: DbSession) -> AccountResponse:
    _ensure_platform(platform)
    account = ensure_jd_account(db, request.app.state.settings)
    await check_account(account.id, request.app.state.browser)
    db.refresh(account)
    return AccountResponse.model_validate(account)
