import time
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import Product
from app.core.schemas import (
    ListingCreate,
    ListingPriceSeries,
    PricePoint,
    ProductBatchCreateRequest,
    ProductCreateRequest,
    ProductDetail,
    ProductMonitoringPatch,
    ProductSummary,
)
from app.services.accounts import ensure_platform_account
from app.services.catalog import (
    add_listing_to_product,
    create_product_with_listing,
    create_product_with_listings,
    list_products,
    listing_price_series,
    price_points,
    product_detail,
    product_summary,
)
from app.services.checkout import start_checkout_calibration
from app.services.monitor import poll_product

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]

_MANUAL_REFRESH_COOLDOWN_SECONDS = 120
_last_manual_refresh: dict[int, float] = {}


@router.get("/products", response_model=list[ProductSummary])
def get_products(db: DbSession) -> list[ProductSummary]:
    return list_products(db)


@router.post("/products", response_model=ProductSummary)
def create_product(payload: ProductCreateRequest, db: DbSession) -> ProductSummary:
    try:
        product = create_product_with_listing(db, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return product_summary(db, product)


@router.post("/products/batch", response_model=ProductSummary)
def create_product_batch(payload: ProductBatchCreateRequest, db: DbSession) -> ProductSummary:
    try:
        product = create_product_with_listings(db, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return product_summary(db, product)


@router.post("/products/{product_id}/listings", response_model=ProductDetail)
def bind_listing(product_id: int, payload: ListingCreate, db: DbSession) -> ProductDetail:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    try:
        add_listing_to_product(db, product, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.refresh(product)
    return product_detail(db, product)


@router.get("/products/{product_id}", response_model=ProductDetail)
def get_product(product_id: int, db: DbSession) -> ProductDetail:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    return product_detail(db, product)


@router.patch("/products/{product_id}/monitoring", response_model=ProductSummary)
def update_product_monitoring(
    product_id: int, payload: ProductMonitoringPatch, db: DbSession
) -> ProductSummary:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    product.monitoring_enabled = payload.enabled
    db.commit()
    db.refresh(product)
    return product_summary(db, product)


def _range_since(range_: str) -> datetime | None:
    days = {"7d": 7, "30d": 30, "90d": 90}
    if range_ == "all":
        return None
    if range_ in days:
        return datetime.now(UTC) - timedelta(days=days[range_])
    raise HTTPException(status_code=422, detail="range 只支持 7d/30d/90d/all")


@router.get("/products/{product_id}/prices", response_model=list[PricePoint])
def get_prices(
    product_id: int,
    db: DbSession,
    range_: str = Query("30d", alias="range"),
) -> list[PricePoint]:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    return price_points(db, product_id, _range_since(range_))


@router.get(
    "/products/{product_id}/listing-prices",
    response_model=list[ListingPriceSeries],
)
def get_listing_prices(
    product_id: int,
    db: DbSession,
    range_: str = Query("30d", alias="range"),
) -> list[ListingPriceSeries]:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    return listing_price_series(db, product_id, _range_since(range_))


@router.post("/products/{product_id}/refresh")
def refresh_product(
    product_id: int,
    background_tasks: BackgroundTasks,
    db: DbSession,
) -> dict[str, bool]:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    if not product.monitoring_enabled:
        raise HTTPException(status_code=409, detail="商品监测已暂停，请先开启监测")
    if not any(listing.status == "active" for listing in product.listings):
        raise HTTPException(status_code=409, detail="没有可监测的链接，请先恢复商品链接")

    now = time.monotonic()
    last = _last_manual_refresh.get(product_id, 0.0)
    if now - last < _MANUAL_REFRESH_COOLDOWN_SECONDS:
        raise HTTPException(
            status_code=429,
            detail="抓取太频繁，请稍后再试（建议等待自动轮询）",
        )
    _last_manual_refresh[product_id] = now

    background_tasks.add_task(poll_product, product_id)
    return {"queued": True}


@router.post("/products/{product_id}/checkout-calibrate")
def calibrate_product(
    product_id: int,
    request: Request,
    db: DbSession,
) -> dict[str, object]:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")

    started = []
    for listing in product.listings:
        if listing.status != "active":
            continue
        account = ensure_platform_account(
            db, request.app.state.settings, listing.platform
        )
        if account.status != "logged_in":
            continue
        if start_checkout_calibration(listing.id):
            started.append(listing.id)
    return {
        "started": len(started),
        "listing_ids": started,
        "message": (
            "已打开结算预览窗口；如未自动进入确认页，请手动点击“立即购买”。不会提交订单。"
            if started
            else "没有可校准的链接，或校准正在进行/冷却中"
        ),
    }


@router.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int, db: DbSession) -> None:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    db.delete(product)
    db.commit()
