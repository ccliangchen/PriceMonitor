import type { ApiResponse, AppInfo } from '@/types/global'
import type {
  Account,
  AppSettings,
  Health,
  JobRun,
  ListingPayload,
  ListingPriceSeries,
  ModelSearchResponse,
  NotificationStatus,
  PricePoint,
  PriceRange,
  ProductCreatePayload,
  ProductDetail,
  ProductSummary,
  ListingResolve,
  SearchPlatform
} from './types'

function requireApi(): Window['api'] {
  if (typeof window === 'undefined' || !window.api) {
    throw new Error('请通过 PriceMonitor 桌面应用启动')
  }
  return window.api
}

export async function apiRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response: ApiResponse = await requireApi().request(method, path, body)
  if (!response.ok) {
    const payload = response.data as { detail?: unknown } | null
    const detail = typeof payload?.detail === 'string' ? payload.detail : null
    if (detail) {
      throw new Error(detail)
    }
    if (response.error) {
      throw new Error(response.error)
    }
    if (response.status === 422) {
      throw new Error('请求参数不正确，请检查输入')
    }
    throw new Error(`请求失败（HTTP ${response.status}）`)
  }
  return response.data as T
}

export async function getAppInfo(): Promise<AppInfo> {
  return requireApi().getAppInfo()
}

export function fetchHealth(): Promise<Health> {
  return apiRequest<Health>('GET', '/api/v1/health')
}

export function fetchSettings(): Promise<AppSettings> {
  return apiRequest<AppSettings>('GET', '/api/v1/settings')
}

export function updateSettings(patch: Partial<AppSettings>): Promise<AppSettings> {
  return apiRequest<AppSettings>('PATCH', '/api/v1/settings', patch)
}

export function fetchAccounts(): Promise<Account[]> {
  return apiRequest<Account[]>('GET', '/api/v1/accounts')
}

export function startLogin(platform: string): Promise<{ started: boolean; message: string }> {
  return apiRequest('POST', `/api/v1/accounts/${platform}/login`)
}

export function logoutAccount(platform: string): Promise<Account> {
  return apiRequest<Account>('POST', `/api/v1/accounts/${platform}/logout`)
}

export function checkAccount(platform: string): Promise<Account> {
  return apiRequest<Account>('POST', `/api/v1/accounts/${platform}/check`)
}

export function resolveListing(url: string): Promise<ListingResolve> {
  return apiRequest<ListingResolve>('POST', '/api/v1/listings/resolve', { url })
}

export function searchModel(
  query: string,
  platform: SearchPlatform = 'jd'
): Promise<ModelSearchResponse> {
  return apiRequest<ModelSearchResponse>('POST', '/api/v1/listings/search-model', {
    query,
    platform
  })
}

export function createProduct(payload: ProductCreatePayload): Promise<ProductSummary> {
  return apiRequest<ProductSummary>('POST', '/api/v1/products', payload)
}

export function bindListing(
  productId: number,
  listing: ListingPayload
): Promise<ProductDetail> {
  return apiRequest<ProductDetail>('POST', `/api/v1/products/${productId}/listings`, listing)
}

export function fetchProducts(): Promise<ProductSummary[]> {
  return apiRequest<ProductSummary[]>('GET', '/api/v1/products')
}

export function fetchProduct(productId: number): Promise<ProductDetail> {
  return apiRequest<ProductDetail>('GET', `/api/v1/products/${productId}`)
}

export function fetchPrices(productId: number, range: PriceRange): Promise<PricePoint[]> {
  return apiRequest<PricePoint[]>('GET', `/api/v1/products/${productId}/prices?range=${range}`)
}

export function fetchListingPrices(
  productId: number,
  range: PriceRange
): Promise<ListingPriceSeries[]> {
  return apiRequest<ListingPriceSeries[]>(
    'GET',
    `/api/v1/products/${productId}/listing-prices?range=${range}`
  )
}

export function refreshProduct(productId: number): Promise<{ queued: boolean }> {
  return apiRequest('POST', `/api/v1/products/${productId}/refresh`)
}

export function verifyListing(
  listingId: number
): Promise<{ started: boolean; message: string }> {
  return apiRequest('POST', `/api/v1/listings/${listingId}/verify`)
}

export function calibrateListing(
  listingId: number
): Promise<{ started: boolean; message: string }> {
  return apiRequest('POST', `/api/v1/listings/${listingId}/checkout-calibrate`)
}

export function updateListing(
  listingId: number,
  status: 'active' | 'paused'
): Promise<{ id: number; status: string }> {
  return apiRequest('PATCH', `/api/v1/listings/${listingId}`, { status })
}

export function calibrateProduct(
  productId: number
): Promise<{ started: number; listing_ids: number[]; message: string }> {
  return apiRequest('POST', `/api/v1/products/${productId}/checkout-calibrate`)
}

export async function deleteProduct(productId: number): Promise<void> {
  await apiRequest('DELETE', `/api/v1/products/${productId}`)
}

export function fetchJobs(): Promise<JobRun[]> {
  return apiRequest<JobRun[]>('GET', '/api/v1/jobs')
}

export function fetchNotificationStatus(): Promise<NotificationStatus> {
  return apiRequest<NotificationStatus>('GET', '/api/v1/notifications/status')
}

export function saveServerchanKey(sendkey: string): Promise<NotificationStatus> {
  return apiRequest<NotificationStatus>('PUT', '/api/v1/notifications/serverchan', {
    serverchan_sendkey: sendkey
  })
}

export function testNotification(): Promise<{ sent: boolean }> {
  return apiRequest('POST', '/api/v1/notifications/test')
}
