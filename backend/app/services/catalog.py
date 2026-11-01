from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.adapters.base import ListingInfo
from app.core.exceptions import ShopNotAllowed
from app.core.models import (
    JobRun,
    Listing,
    PriceSnapshot,
    Product,
    ProductPriceSnapshot,
)
from app.core.price_engine import history_low_cents, latest_product_snapshot
from app.core.schemas import (
    ListingCreate,
    ListingDetail,
    ListingPricePoint,
    ListingPriceSeries,
    PricePoint,
    ProductCreateRequest,
    ProductDetail,
    ProductSummary,
)
from app.core.shop_policy import ShopDecision, evaluate_shop


def canonical_key(
    brand: str,
    model: str,
    variant: str,
    ram_gb: int,
    storage_gb: int,
    color: str | None,
) -> str:
    parts = [brand, model, variant, str(ram_gb), str(storage_gb), color or ""]
    return "|".join(part.strip().lower() for part in parts)


def create_product_with_listing(db: Session, payload: ProductCreateRequest) -> Product:
    info = ListingInfo(
        platform=payload.listing.platform,
        url=payload.listing.url,
        title=payload.listing.title,
        shop_name=payload.listing.shop_name,
        shop_type=payload.listing.shop_type,
        platform_item_id=payload.listing.platform_item_id,
        platform_sku_id=payload.listing.platform_sku_id,
        detected_specs=payload.listing.detected_specs,
        evidence=payload.listing.shop_evidence,
    )
    decision = evaluate_shop(info, payload.brand)
    if decision.decision != ShopDecision.ALLOWED:
        raise ShopNotAllowed(decision.reason)

    duplicate = db.scalar(
        select(Listing).where(
            Listing.platform == payload.listing.platform,
            Listing.platform_item_id == payload.listing.platform_item_id,
            Listing.platform_sku_id == payload.listing.platform_sku_id,
        )
    )
    if duplicate is not None:
        raise ValueError("该商品链接已经添加过了")

    key = canonical_key(
        payload.brand,
        payload.model,
        payload.variant,
        payload.ram_gb,
        payload.storage_gb,
        payload.color,
    )
    product = db.scalar(select(Product).where(Product.canonical_key == key))
    if product is None:
        product = Product(
            name=payload.name,
            brand=payload.brand,
            model=payload.model,
            variant=payload.variant,
            ram_gb=payload.ram_gb,
            storage_gb=payload.storage_gb,
            color=payload.color,
            canonical_key=key,
            notes=payload.notes,
        )
        db.add(product)
        db.flush()

    listing = Listing(
        product_id=product.id,
        platform=payload.listing.platform,
        shop_name=payload.listing.shop_name,
        shop_type=payload.listing.shop_type,
        shop_verified=True,
        shop_evidence=payload.listing.shop_evidence,
        url=payload.listing.url,
        platform_item_id=payload.listing.platform_item_id,
        platform_sku_id=payload.listing.platform_sku_id,
        title=payload.listing.title,
        status="active",
    )
    db.add(listing)
    db.commit()
    db.refresh(product)
    return product


def add_listing_to_product(db: Session, product: Product, payload: ListingCreate) -> Listing:
    info = ListingInfo(
        platform=payload.platform,
        url=payload.url,
        title=payload.title,
        shop_name=payload.shop_name,
        shop_type=payload.shop_type,
        platform_item_id=payload.platform_item_id,
        platform_sku_id=payload.platform_sku_id,
        detected_specs=payload.detected_specs,
        evidence=payload.shop_evidence,
    )
    decision = evaluate_shop(info, product.brand)
    if decision.decision != ShopDecision.ALLOWED:
        raise ShopNotAllowed(decision.reason)

    duplicate = db.scalar(
        select(Listing).where(
            Listing.platform == payload.platform,
            Listing.platform_item_id == payload.platform_item_id,
            Listing.platform_sku_id == payload.platform_sku_id,
        )
    )
    if duplicate is not None:
        raise ValueError("该商品链接已经添加过了")

    listing = Listing(
        product_id=product.id,
        platform=payload.platform,
        shop_name=payload.shop_name,
        shop_type=payload.shop_type,
        shop_verified=True,
        shop_evidence=payload.shop_evidence,
        url=payload.url,
        platform_item_id=payload.platform_item_id,
        platform_sku_id=payload.platform_sku_id,
        title=payload.title,
        status="active",
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return listing


def _low_by_source(db: Session, product_id: int, source: str) -> int | None:
    return db.scalar(
        select(func.min(PriceSnapshot.effective_price_cents))
        .join(Listing, PriceSnapshot.listing_id == Listing.id)
        .where(
            Listing.product_id == product_id,
            PriceSnapshot.source == source,
            PriceSnapshot.status == "ok",
            PriceSnapshot.effective_price_cents > 0,
            or_(
                PriceSnapshot.confidence.is_(None),
                PriceSnapshot.confidence != "low",
            ),
        )
    )


def _last_checkout_at(db: Session, product_id: int) -> datetime | None:
    return db.scalar(
        select(func.max(PriceSnapshot.captured_at))
        .join(Listing, PriceSnapshot.listing_id == Listing.id)
        .where(
            Listing.product_id == product_id,
            PriceSnapshot.source == "checkout",
            PriceSnapshot.status == "ok",
        )
    )


def product_summary(db: Session, product: Product) -> ProductSummary:
    latest = latest_product_snapshot(db, product.id)
    history_low = history_low_cents(db, product.id)
    listings = list(product.listings)
    checked = [item.last_checked_at for item in listings if item.last_checked_at is not None]
    last_checked = max(checked) if checked else None
    statuses = {item.status for item in listings}
    if "active" in statuses:
        status = "active"
    elif "needs_review" in statuses:
        status = "needs_review"
    elif "error" in statuses:
        status = "error"
    else:
        status = "paused"

    current_source = None
    current_confidence = None
    if latest is not None and isinstance(latest.source_mix, dict):
        current_source = latest.source_mix.get(latest.lowest_platform)
        latest_low = db.scalar(
            select(PriceSnapshot)
            .where(
                PriceSnapshot.listing_id == latest.lowest_listing_id,
                PriceSnapshot.status == "ok",
                or_(
                    PriceSnapshot.confidence.is_(None),
                    PriceSnapshot.confidence != "low",
                ),
            )
            .order_by(PriceSnapshot.captured_at.desc(), PriceSnapshot.id.desc())
            .limit(1)
        )
        if latest_low is not None:
            current_confidence = latest_low.confidence

    return ProductSummary(
        id=product.id,
        name=product.name,
        brand=product.brand,
        model=product.model,
        variant=product.variant,
        ram_gb=product.ram_gb,
        storage_gb=product.storage_gb,
        color=product.color,
        current_price_cents=latest.lowest_price_cents if latest else None,
        current_platform=latest.lowest_platform if latest else None,
        current_source=current_source,
        current_confidence=current_confidence,
        history_low_cents=history_low,
        page_low_cents=_low_by_source(db, product.id, "page"),
        checkout_low_cents=_low_by_source(db, product.id, "checkout"),
        checkout_last_at=_last_checkout_at(db, product.id),
        last_checked_at=last_checked,
        listing_count=len(listings),
        status=status,
        created_at=product.created_at,
    )


def product_detail(db: Session, product: Product) -> ProductDetail:
    summary = product_summary(db, product)
    listings = []
    for item in product.listings:
        latest_attempt = db.scalar(
            select(PriceSnapshot)
            .where(PriceSnapshot.listing_id == item.id)
            .order_by(PriceSnapshot.captured_at.desc(), PriceSnapshot.id.desc())
            .limit(1)
        )
        latest_ok = db.scalar(
            select(PriceSnapshot)
            .where(
                PriceSnapshot.listing_id == item.id,
                PriceSnapshot.status == "ok",
                or_(
                    PriceSnapshot.confidence.is_(None),
                    PriceSnapshot.confidence != "low",
                ),
            )
            .order_by(PriceSnapshot.captured_at.desc(), PriceSnapshot.id.desc())
            .limit(1)
        )
        latest_checkout = db.scalar(
            select(PriceSnapshot)
            .where(
                PriceSnapshot.listing_id == item.id,
                PriceSnapshot.source == "checkout",
                PriceSnapshot.status == "ok",
            )
            .order_by(PriceSnapshot.captured_at.desc(), PriceSnapshot.id.desc())
            .limit(1)
        )
        checkout_job = db.scalar(
            select(JobRun)
            .where(JobRun.listing_id == item.id, JobRun.job_type == "checkout")
            .order_by(JobRun.started_at.desc(), JobRun.id.desc())
            .limit(1)
        )
        listings.append(
            ListingDetail(
                id=item.id,
                platform=item.platform,
                url=item.url,
                title=item.title,
                shop_name=item.shop_name,
                shop_type=item.shop_type,
                shop_verified=item.shop_verified,
                status=item.status,
                last_checked_at=item.last_checked_at,
                page_price_cents=latest_ok.page_price_cents if latest_ok else None,
                estimated_price_cents=latest_ok.estimated_price_cents if latest_ok else None,
                checkout_price_cents=(
                    latest_checkout.checkout_price_cents if latest_checkout else None
                ),
                effective_price_cents=latest_ok.effective_price_cents if latest_ok else None,
                price_source=latest_ok.source if latest_ok else None,
                price_confidence=latest_ok.confidence if latest_ok else None,
                coupon_breakdown=(latest_ok.coupon_breakdown or []) if latest_ok else [],
                price_captured_at=latest_ok.captured_at if latest_ok else None,
                checkout_captured_at=(
                    latest_checkout.captured_at if latest_checkout else None
                ),
                last_attempt_status=latest_attempt.status if latest_attempt else None,
                last_attempt_error=latest_attempt.error_message if latest_attempt else None,
                last_attempt_at=latest_attempt.captured_at if latest_attempt else None,
                last_checkout_status=checkout_job.status if checkout_job else None,
                last_checkout_error=checkout_job.error_message if checkout_job else None,
                last_checkout_at=checkout_job.started_at if checkout_job else None,
            )
        )
    recent = db.scalars(
        select(ProductPriceSnapshot)
        .where(ProductPriceSnapshot.product_id == product.id)
        .order_by(ProductPriceSnapshot.captured_at.desc(), ProductPriceSnapshot.id.desc())
        .limit(200)
    ).all()
    points = [
        PricePoint(
            captured_at=item.captured_at,
            lowest_price_cents=item.lowest_price_cents,
            lowest_platform=item.lowest_platform,
        )
        for item in reversed(recent)
    ]
    return ProductDetail(
        **summary.model_dump(),
        listings=listings,
        recent_prices=points,
    )


def price_points(
    db: Session,
    product_id: int,
    since: datetime | None = None,
) -> list[PricePoint]:
    query = select(ProductPriceSnapshot).where(
        ProductPriceSnapshot.product_id == product_id
    )
    if since is not None:
        query = query.where(ProductPriceSnapshot.captured_at >= since)
    rows = db.scalars(
        query.order_by(ProductPriceSnapshot.captured_at.asc(), ProductPriceSnapshot.id.asc())
    ).all()
    return [
        PricePoint(
            captured_at=item.captured_at,
            lowest_price_cents=item.lowest_price_cents,
            lowest_platform=item.lowest_platform,
        )
        for item in rows
    ]


def listing_price_series(
    db: Session,
    product_id: int,
    since: datetime | None = None,
) -> list[ListingPriceSeries]:
    listings = db.scalars(
        select(Listing)
        .where(Listing.product_id == product_id)
        .order_by(Listing.id)
    ).all()
    result: list[ListingPriceSeries] = []
    for listing in listings:
        query = select(PriceSnapshot).where(
            PriceSnapshot.listing_id == listing.id,
            PriceSnapshot.status == "ok",
            PriceSnapshot.effective_price_cents > 0,
        )
        if since is not None:
            query = query.where(PriceSnapshot.captured_at >= since)
        rows = db.scalars(
            query.order_by(
                PriceSnapshot.captured_at.asc(),
                PriceSnapshot.id.asc(),
            )
        ).all()
        if not rows:
            continue
        result.append(
            ListingPriceSeries(
                listing_id=listing.id,
                platform=listing.platform,
                shop_name=listing.shop_name,
                points=[
                    ListingPricePoint(
                        captured_at=row.captured_at,
                        effective_price_cents=row.effective_price_cents,
                        source=row.source,
                    )
                    for row in rows
                ],
            )
        )
    return result


def list_products(db: Session) -> list[ProductSummary]:
    products = db.scalars(select(Product).order_by(Product.created_at.desc())).all()
    return [product_summary(db, product) for product in products]
