export interface Health {
  status: 'ok'
  version: string
  uptime_seconds: number
  data_dir: string
  database: 'ok' | 'error'
}

export type NotificationChannel = 'serverchan' | 'pushplus'

export interface AppSettings {
  poll_interval_minutes: number
  checkout_interval_hours: number
  close_to_tray: boolean
  auto_start: boolean
  notification_channel: NotificationChannel
  history_retention_days: number
  notification_configured: boolean
}

export interface Account {
  id: number
  platform: string
  display_name: string
  status: string
  last_login_at: string | null
}

export interface ListingResolve {
  platform: string
  url: string
  title: string
  shop_name: string
  shop_type: 'official_flagship' | 'jd_official_self' | 'other' | 'unknown'
  platform_item_id: string
  platform_sku_id: string | null
  detected_specs: Record<string, string>
  evidence: Record<string, string>
  decision: 'allowed' | 'rejected' | 'needs_review'
  decision_reason: string
}

export interface ListingPayload {
  platform: 'jd' | 'taobao'
  url: string
  title: string
  shop_name: string
  shop_type: ListingResolve['shop_type']
  platform_item_id: string
  platform_sku_id: string | null
  shop_evidence: Record<string, string>
  detected_specs: Record<string, string>
}

export interface ProductCreatePayload {
  name: string
  brand: string
  model: string
  variant: string
  ram_gb: number
  storage_gb: number
  color: string | null
  notes: string | null
  listing: ListingPayload
}

export interface ProductSummary {
  id: number
  name: string
  brand: string
  model: string
  variant: string
  ram_gb: number
  storage_gb: number
  color: string | null
  current_price_cents: number | null
  current_platform: string | null
  current_source: string | null
  current_confidence: string | null
  history_low_cents: number | null
  page_low_cents: number | null
  checkout_low_cents: number | null
  checkout_last_at: string | null
  last_checked_at: string | null
  listing_count: number
  status: string
  created_at: string
}

export interface ListingDetail {
  id: number
  platform: string
  url: string
  title: string
  shop_name: string
  shop_type: string
  shop_verified: boolean
  status: string
  last_checked_at: string | null
  page_price_cents: number | null
  estimated_price_cents: number | null
  checkout_price_cents: number | null
  effective_price_cents: number | null
  price_source: string | null
  price_confidence: string | null
  coupon_breakdown: Array<Record<string, unknown>>
  price_captured_at: string | null
  checkout_captured_at: string | null
  last_attempt_status: string | null
  last_attempt_error: string | null
  last_attempt_at: string | null
  last_checkout_status: string | null
  last_checkout_error: string | null
  last_checkout_at: string | null
}

export interface PricePoint {
  captured_at: string
  lowest_price_cents: number
  lowest_platform: string
}

export interface ListingPricePoint {
  captured_at: string
  effective_price_cents: number
  source: string
}

export interface ListingPriceSeries {
  listing_id: number
  platform: string
  shop_name: string
  points: ListingPricePoint[]
}

export interface ProductDetail extends ProductSummary {
  listings: ListingDetail[]
  recent_prices: PricePoint[]
}

export interface JobRun {
  id: number
  platform: string
  listing_id: number | null
  job_type: string
  started_at: string
  finished_at: string | null
  status: string
  error_message: string | null
}

export interface NotificationStatus {
  serverchan_configured: boolean
}

export type PriceRange = '7d' | '30d' | '90d' | 'all'

export interface ParsedProductQuery {
  brand: string
  model: string
  variant: string
  ram_gb: number | null
  storage_gb: number | null
}

export interface SkuVariantOption {
  ram_gb: number | null
  storage_gb: number | null
  color: string
  spec: string
  sku_id: string
  url: string
}

export interface ModelSearchCandidate {
  store_name: string
  store_type: string
  model_url: string | null
  title: string | null
  requested_available: boolean
  matched_sku_id: string | null
  variants: SkuVariantOption[]
  error: string | null
}

export interface ModelSearchResponse {
  query: ParsedProductQuery
  candidates: ModelSearchCandidate[]
}
