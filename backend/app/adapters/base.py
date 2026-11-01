from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol

from app.core.models import Account, Listing

ShopType = Literal["official_flagship", "jd_official_self", "other", "unknown"]
QuoteStatus = Literal["ok", "captcha", "login_required", "parse_error", "outlier"]
PriceSource = Literal["page", "checkout"]
PriceConfidence = Literal["high", "low"]


@dataclass
class ListingInfo:
    platform: str
    url: str
    title: str
    shop_name: str
    shop_type: ShopType
    platform_item_id: str
    platform_sku_id: str | None = None
    detected_specs: dict[str, str] = field(default_factory=dict)
    evidence: dict[str, str] = field(default_factory=dict)


@dataclass
class PriceQuote:
    platform: str
    listing_id: int
    source: PriceSource
    effective_price_cents: int
    confidence: PriceConfidence | None = None
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    page_price_cents: int | None = None
    coupon_discount_cents: int | None = None
    estimated_price_cents: int | None = None
    checkout_price_cents: int | None = None
    shipping_cents: int = 0
    coupon_breakdown: list[dict] = field(default_factory=list)
    status: QuoteStatus = "ok"
    error: str | None = None


@dataclass
class LoginStatus:
    logged_in: bool
    message: str = ""
    display_name: str | None = None


class PlatformAdapter(Protocol):
    platform: str

    async def resolve_listing(
        self,
        url: str,
        account: Account | None = None,
    ) -> ListingInfo: ...

    async def fetch_page_price(self, listing: Listing, account: Account) -> PriceQuote: ...

    async def fetch_checkout_price(
        self,
        listing: Listing,
        account: Account,
        headless: bool = False,
    ) -> PriceQuote: ...

    async def check_login(self, account: Account) -> LoginStatus: ...
