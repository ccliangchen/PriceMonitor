import time
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import ShopNotAllowed
from app.core.models import Product
from app.core.schemas import (
    PricePoint,
    ProductCreateRequest,
    ProductDetail,
    ProductSummary,
)
from app.services.catalog import (
    create_product_with_listing,
    list_products,
    price_points,
    product_detail,
    product_summary,
)
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
    except ShopNotAllowed as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return product_summary(db, product)


@router.get("/products/{product_id}", response_model=ProductDetail)
def get_product(product_id: int, db: DbSession) -> ProductDetail:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    return product_detail(db, product)


@router.get("/products/{product_id}/prices", response_model=list[PricePoint])
def get_prices(
    product_id: int,
    db: DbSession,
    range_: str = Query("30d", alias="range"),
) -> list[PricePoint]:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")

    days = {"7d": 7, "30d": 30, "90d": 90}
    if range_ == "all":
        since = None
    elif range_ in days:
        since = datetime.now(UTC) - timedelta(days=days[range_])
    else:
        raise HTTPException(status_code=422, detail="range 只支持 7d/30d/90d/all")

    return price_points(db, product_id, since)


@router.post("/products/{product_id}/refresh")
def refresh_product(
    product_id: int,
    background_tasks: BackgroundTasks,
    db: DbSession,
) -> dict[str, bool]:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")

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


@router.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int, db: DbSession) -> None:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    db.delete(product)
    db.commit()
