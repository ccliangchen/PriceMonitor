from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NotificationChannel = Literal["serverchan", "pushplus"]
Platform = Literal["jd", "taobao"]
ShopTypeName = Literal["official_flagship", "jd_official_self", "other", "unknown"]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    uptime_seconds: int
    data_dir: str
    database: Literal["ok", "error"]


class SettingsResponse(BaseModel):
    poll_interval_minutes: int = 30
    checkout_interval_hours: int = 6
    close_to_tray: bool = True
    auto_start: bool = False
    notification_channel: NotificationChannel = "serverchan"
    history_retention_days: int = 0
    onboarding_completed: bool = False
    notification_configured: bool = False


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    poll_interval_minutes: int | None = Field(default=None, ge=10, le=180)
    checkout_interval_hours: int | None = Field(default=None, ge=4, le=12)
    close_to_tray: bool | None = None
    auto_start: bool | None = None
    notification_channel: NotificationChannel | None = None
    history_retention_days: int | None = Field(default=None, ge=0)
    onboarding_completed: bool | None = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    display_name: str
    status: str
    last_login_at: datetime | None


class LoginStartedResponse(BaseModel):
    started: bool
    message: str


class ListingResolveRequest(BaseModel):
    url: str = Field(min_length=1)


class ListingResolveResponse(BaseModel):
    platform: str
    url: str
    title: str
    shop_name: str
    shop_type: ShopTypeName
    platform_item_id: str
    platform_sku_id: str | None = None
    detected_specs: dict[str, str] = Field(default_factory=dict)
    evidence: dict[str, str] = Field(default_factory=dict)
    decision: str
    decision_reason: str


class ListingCreate(BaseModel):
    platform: Platform
    url: str
    title: str
    shop_name: str
    shop_type: ShopTypeName
    platform_item_id: str
    platform_sku_id: str | None = None
    shop_evidence: dict[str, str] = Field(default_factory=dict)
    detected_specs: dict[str, str] = Field(default_factory=dict)


class ListingPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "paused"] | None = None


class ProductCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    brand: str = Field(min_length=1)
    model: str = Field(min_length=1)
    variant: str = ""
    ram_gb: int = Field(ge=1)
    storage_gb: int = Field(ge=1)
    color: str | None = None
    notes: str | None = None
    listing: ListingCreate


class ProductSummary(BaseModel):
    id: int
    name: str
    brand: str
    model: str
    variant: str
    ram_gb: int
    storage_gb: int
    color: str | None
    current_price_cents: int | None
    current_platform: str | None
    current_source: str | None
    current_confidence: str | None = None
    history_low_cents: int | None
    last_checked_at: datetime | None
    page_low_cents: int | None = None
    checkout_low_cents: int | None = None
    checkout_last_at: datetime | None = None
    listing_count: int
    status: str
    created_at: datetime


class ListingDetail(BaseModel):
    id: int
    platform: str
    url: str
    title: str
    shop_name: str
    shop_type: str
    shop_verified: bool
    status: str
    last_checked_at: datetime | None
    page_price_cents: int | None = None
    estimated_price_cents: int | None = None
    checkout_price_cents: int | None = None
    effective_price_cents: int | None = None
    price_source: str | None = None
    price_confidence: str | None = None
    coupon_breakdown: list[dict] = Field(default_factory=list)
    price_captured_at: datetime | None = None
    checkout_captured_at: datetime | None = None
    last_attempt_status: str | None = None
    last_attempt_error: str | None = None
    last_attempt_at: datetime | None = None
    last_checkout_status: str | None = None
    last_checkout_error: str | None = None
    last_checkout_at: datetime | None = None


class PricePoint(BaseModel):
    captured_at: datetime
    lowest_price_cents: int
    lowest_platform: str


class ListingPricePoint(BaseModel):
    captured_at: datetime
    effective_price_cents: int
    source: str


class ListingPriceSeries(BaseModel):
    listing_id: int
    platform: str
    shop_name: str
    points: list[ListingPricePoint] = Field(default_factory=list)


class ProductDetail(ProductSummary):
    listings: list[ListingDetail] = Field(default_factory=list)
    recent_prices: list[PricePoint] = Field(default_factory=list)


class JobRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    listing_id: int | None
    job_type: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    error_message: str | None


class ModelSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    platform: Platform = "jd"


class ParsedProductQuery(BaseModel):
    brand: str
    model: str
    variant: str
    ram_gb: int | None
    storage_gb: int | None


class SkuVariantOption(BaseModel):
    ram_gb: int | None
    storage_gb: int | None
    color: str
    spec: str
    sku_id: str
    url: str


class ModelSearchCandidate(BaseModel):
    platform: Platform = "jd"
    store_name: str
    store_type: str
    model_url: str | None
    title: str | None
    requested_available: bool = False
    matched_sku_id: str | None = None
    platform_item_id: str | None = None
    shop_evidence: dict[str, str] = Field(default_factory=dict)
    variants: list[SkuVariantOption] = Field(default_factory=list)
    error: str | None = None


class ModelSearchResponse(BaseModel):
    query: ParsedProductQuery
    candidates: list[ModelSearchCandidate] = Field(default_factory=list)


class NotificationConfigRequest(BaseModel):
    serverchan_sendkey: str = Field(min_length=1)


class NotificationStatusResponse(BaseModel):
    serverchan_configured: bool
