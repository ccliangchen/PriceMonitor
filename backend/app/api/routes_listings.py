from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.adapters.registry import get_adapter
from app.core.db import get_db
from app.core.exceptions import (
    CaptchaRequired,
    LoginRequired,
    ParseError,
    RateLimited,
    ShopNotAllowed,
)
from app.core.models import Listing, PriceSnapshot
from app.core.platforms import detect_platform, platform_label
from app.core.schemas import (
    ListingPatch,
    ListingResolveRequest,
    ListingResolveResponse,
    LoginStartedResponse,
)
from app.services.accounts import ensure_platform_account
from app.services.checkout import checkout_cooldown_remaining, start_checkout_calibration
from app.services.listing_resolution import resolve_with_browser_extension
from app.services.verification import start_verification

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]


@router.post("/listings/resolve", response_model=ListingResolveResponse)
async def resolve_listing(
    payload: ListingResolveRequest,
    request: Request,
    db: DbSession,
) -> ListingResolveResponse:
    platform = detect_platform(payload.url)
    if platform is None:
        raise HTTPException(status_code=422, detail="只支持京东、淘宝、天猫商品链接")

    account = ensure_platform_account(db, request.app.state.settings, platform)
    label = platform_label(platform)
    adapter = get_adapter(platform)
    if adapter is None:
        raise HTTPException(status_code=503, detail=f"{label}适配器未注册")

    try:
        if platform == "jd":
            info = await resolve_with_browser_extension(platform, payload.url)
            source = "selected_browser"
        elif account.status == "logged_in":
            try:
                info = await adapter.resolve_listing(payload.url, account)
                source = "app_browser"
            except (LoginRequired, CaptchaRequired, RateLimited, ParseError) as direct_error:
                logger.warning(
                    "Taobao link direct resolve failed ({}); starting selected browser if needed",
                    direct_error,
                )
                info = await resolve_with_browser_extension(platform, payload.url)
                source = "selected_browser"
        else:
            info = await resolve_with_browser_extension(platform, payload.url)
            source = "selected_browser"
    except LoginRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CaptchaRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RateLimited as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ShopNotAllowed as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to resolve listing")
        raise HTTPException(status_code=502, detail=f"解析{label}商品失败：{exc}") from exc

    logger.info("Resolved {} link item={} via {}", platform, info.platform_item_id, source)

    return ListingResolveResponse(
        platform=info.platform,
        url=info.url,
        title=info.title,
        shop_name=info.shop_name,
        shop_type=info.shop_type,
        platform_item_id=info.platform_item_id,
        platform_sku_id=info.platform_sku_id,
        detected_specs=info.detected_specs,
        evidence=info.evidence,
        decision="allowed",
        decision_reason="商品链接已解析；店铺类型不影响监测",
    )


@router.patch("/listings/{listing_id}")
def update_listing(
    listing_id: int,
    payload: ListingPatch,
    db: DbSession,
) -> dict[str, object]:
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="商品链接不存在")

    if payload.status is not None:
        listing.status = payload.status
        if payload.status == "active":
            if listing.platform == "taobao":
                listing.capture_mode = "primary"
            # Clear stale failure records so the consecutive-failure counter
            # starts from zero after a manual resume.
            db.execute(
                delete(PriceSnapshot).where(
                    PriceSnapshot.listing_id == listing_id,
                    PriceSnapshot.status != "ok",
                )
            )
        db.commit()

    return {"id": listing.id, "status": listing.status}


@router.post(
    "/listings/{listing_id}/checkout-calibrate",
    response_model=LoginStartedResponse,
)
def checkout_calibrate(
    listing_id: int,
    request: Request,
    db: DbSession,
) -> LoginStartedResponse:
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="商品链接不存在")

    account = ensure_platform_account(db, request.app.state.settings, listing.platform)
    if account.status != "logged_in":
        raise HTTPException(status_code=409, detail="账号未登录，无法校准结算价")

    remaining = checkout_cooldown_remaining(listing_id)
    if remaining > 0:
        raise HTTPException(
            status_code=429,
            detail=f"结算校准太频繁，请 {max(1, remaining // 60)} 分钟后再试",
        )

    started = start_checkout_calibration(listing_id)
    return LoginStartedResponse(
        started=started,
        message=(
            "已打开结算预览窗口；如未自动进入确认页，请手动点击“立即购买”。不会提交订单。"
            if started
            else "结算校准已经在运行"
        ),
    )


@router.post("/listings/{listing_id}/verify", response_model=LoginStartedResponse)
async def verify_listing(
    listing_id: int,
    request: Request,
    db: DbSession,
) -> LoginStartedResponse:
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="商品链接不存在")
    started = start_verification(listing_id, request.app.state.browser)
    return LoginStartedResponse(
        started=started,
        message=(
            "已打开京东验证窗口，请完成滑块/验证"
            if started
            else "验证窗口已经在运行，请完成验证"
        ),
    )
