from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.adapters.base import ListingInfo
from app.core.models import (
    JobRun,
    Listing,
    PriceSnapshot,
    Product,
    ProductPriceSnapshot,
)
from app.core.platforms import detect_platform
from app.core.price_engine import (
    latest_product_snapshot,
    plausible_page_price_clause,
    plausible_product_snapshot_clause,
)
from app.core.schemas import (
    ListingCreate,
    ListingDetail,
    ListingPricePoint,
    ListingPriceSeries,
    PricePoint,
    ProductBatchCreateRequest,
    ProductCreateRequest,
    ProductDetail,
    ProductSummary,
)


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
    if not payload.name.strip():
        raise ValueError("请填写商品名称")
    product = Product(
        name=payload.name.strip(), brand=payload.brand, model=payload.model,
        variant=payload.variant, ram_gb=payload.ram_gb,
        storage_gb=payload.storage_gb, color=payload.color,
        canonical_key=f"manual:{uuid4().hex}", notes=payload.notes,
    )
    db.add(product)
    db.flush()
    if payload.listing is not None:
        add_listing_to_product(db, product, payload.listing, commit=False)
    db.commit()
    db.refresh(product)
    return product


def create_product_with_listings(db: Session, payload: ProductBatchCreateRequest) -> Product:
    """Create a user-named product with the explicitly supplied links."""
    if not payload.name.strip():
        raise ValueError("请填写商品名称")
    product = Product(
        name=payload.name.strip(), brand=payload.brand, model=payload.model,
        variant=payload.variant, ram_gb=payload.ram_gb,
        storage_gb=payload.storage_gb, color=payload.color,
        canonical_key=f"manual:{uuid4().hex}", notes=payload.notes,
    )
    db.add(product)
    db.flush()
    seen: set[tuple[str, str, str | None]] = set()
    for item in payload.listings:
        identity = (item.platform, item.platform_item_id, item.platform_sku_id)
        if identity not in seen:
            add_listing_to_product(db, product, item, commit=False)
            seen.add(identity)
    db.commit()
    db.refresh(product)
    return product


def add_listing_to_product(
    db: Session, product: Product, payload: ListingCreate, *, commit: bool = True,
) -> Listing:
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
    if (
        info.platform not in ("jd", "taobao")
        or detect_platform(info.url) != info.platform
        or not info.platform_item_id
    ):
        raise ValueError("链接不是受支持的商品详情页")

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
    if commit:
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
            plausible_page_price_clause(),
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
    history_record = db.scalar(
        select(PriceSnapshot)
        .join(Listing, PriceSnapshot.listing_id == Listing.id)
        .where(
            Listing.product_id == product.id,
            PriceSnapshot.status == "ok",
            PriceSnapshot.effective_price_cents > 0,
            plausible_page_price_clause(),
            or_(PriceSnapshot.confidence.is_(None), PriceSnapshot.confidence != "low"),
        )
        .order_by(PriceSnapshot.effective_price_cents, PriceSnapshot.id)
        .limit(1)
    )
    history_low = history_record.effective_price_cents if history_record else None
    page_low_record = db.scalar(
        select(PriceSnapshot)
        .join(Listing, PriceSnapshot.listing_id == Listing.id)
        .where(
            Listing.product_id == product.id,
            PriceSnapshot.source == "page",
            PriceSnapshot.status == "ok",
            PriceSnapshot.effective_price_cents > 0,
            plausible_page_price_clause(),
            or_(PriceSnapshot.confidence.is_(None), PriceSnapshot.confidence != "low"),
        )
        .order_by(PriceSnapshot.effective_price_cents, PriceSnapshot.id)
        .limit(1)
    )
    listing_by_id = {item.id: item for item in product.listings}
    historical_listing = listing_by_id.get(history_record.listing_id) if history_record else None
    page_listing = listing_by_id.get(page_low_record.listing_id) if page_low_record else None
    listings = list(product.listings)
    checked = [item.last_checked_at for item in listings if item.last_checked_at is not None]
    last_checked = max(checked) if checked else None
    statuses = {item.status for item in listings}
    if not statuses:
        status = "empty"
    elif "active" in statuses:
        status = "active"
    elif "needs_review" in statuses:
        status = "needs_review"
    elif "error" in statuses:
        status = "error"
    else:
        status = "paused"
    if not product.monitoring_enabled:
        status = "paused"

    current_candidates: list[tuple[Listing, PriceSnapshot]] = []
    for listing in listings:
        observed = db.scalar(
            select(PriceSnapshot)
            .where(
                PriceSnapshot.listing_id == listing.id,
                PriceSnapshot.status == "ok",
                PriceSnapshot.effective_price_cents > 0,
                plausible_page_price_clause(),
                or_(
                    PriceSnapshot.confidence.is_(None),
                    PriceSnapshot.confidence != "low",
                ),
            )
            .order_by(PriceSnapshot.captured_at.desc(), PriceSnapshot.id.desc())
            .limit(1)
        )
        if observed is not None:
            current_candidates.append((listing, observed))
    current = min(
        current_candidates, key=lambda item: item[1].effective_price_cents,
        default=None,
    )
    current_listing = current[0] if current else None
    if current_listing is None and latest is not None:
        current_listing = listing_by_id.get(latest.lowest_listing_id)
    current_snapshot = current[1] if current else None
    current_source = current_snapshot.source if current_snapshot else None
    if current_source is None and latest is not None and isinstance(latest.source_mix, dict):
        current_source = latest.source_mix.get(latest.lowest_platform)

    return ProductSummary(
        id=product.id,
        name=product.name,
        brand=product.brand,
        model=product.model,
        variant=product.variant,
        ram_gb=product.ram_gb,
        storage_gb=product.storage_gb,
        color=product.color,
        current_price_cents=(
            current_snapshot.effective_price_cents if current_snapshot else
            latest.lowest_price_cents if latest else None
        ),
        current_platform=current_listing.platform if current_listing else None,
        current_shop_name=current_listing.shop_name if current_listing else None,
        current_source=current_source,
        current_confidence=current_snapshot.confidence if current_snapshot else None,
        history_low_cents=history_low,
        history_low_platform=historical_listing.platform if historical_listing else None,
        history_low_shop_name=historical_listing.shop_name if historical_listing else None,
        page_low_cents=_low_by_source(db, product.id, "page"),
        page_low_platform=page_listing.platform if page_listing else None,
        page_low_shop_name=page_listing.shop_name if page_listing else None,
        checkout_low_cents=_low_by_source(db, product.id, "checkout"),
        checkout_last_at=_last_checkout_at(db, product.id),
        last_checked_at=last_checked,
        listing_count=len(listings),
        monitoring_enabled=product.monitoring_enabled,
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
        latest_implausible = bool(
            latest_attempt
            and latest_attempt.status == "ok"
            and latest_attempt.source == "page"
            and latest_attempt.page_price_cents
            and latest_attempt.effective_price_cents * 4 < latest_attempt.page_price_cents
        )
        latest_ok = db.scalar(
            select(PriceSnapshot)
            .where(
                PriceSnapshot.listing_id == item.id,
                PriceSnapshot.status == "ok",
                plausible_page_price_clause(),
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
                capture_mode=item.capture_mode,
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
                last_attempt_status=(
                    "low_confidence"
                    if latest_implausible or (
                        latest_attempt and latest_attempt.status == "ok" and latest_attempt.confidence == "low"
                    )
                    else latest_attempt.status if latest_attempt else None
                ),
                last_attempt_error=(
                    "页面预估价远低于同页标价，本轮价格未采纳"
                    if latest_implausible else
                    latest_attempt.error_message or "页面优惠未能核实，本轮价格未采纳"
                    if latest_attempt and latest_attempt.status == "ok" and latest_attempt.confidence == "low"
                    else latest_attempt.error_message if latest_attempt else None
                ),
                last_attempt_at=latest_attempt.captured_at if latest_attempt else None,
                last_checkout_status=checkout_job.status if checkout_job else None,
                last_checkout_error=checkout_job.error_message if checkout_job else None,
                last_checkout_at=checkout_job.started_at if checkout_job else None,
            )
        )
    recent = db.scalars(
        select(ProductPriceSnapshot)
        .where(
            ProductPriceSnapshot.product_id == product.id,
            plausible_product_snapshot_clause(),
        )
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
        ProductPriceSnapshot.product_id == product_id,
        plausible_product_snapshot_clause(),
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
            plausible_page_price_clause(),
            or_(
                PriceSnapshot.confidence.is_(None),
                PriceSnapshot.confidence != "low",
            ),
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
