import type { ApiResponse, AppInfo } from '@/types/global'
import type {
  Account,
  AppSettings,
  Health,
  JobRun,
  ModelSearchResponse,
  NotificationStatus,
  PricePoint,
  PriceRange,
  ProductCreatePayload,
  ProductDetail,
  ProductSummary,
  ListingResolve
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
    const detail = (response.data as { detail?: string } | null)?.detail
    throw new Error(detail ?? response.error ?? `请求失败（HTTP ${response.status}）`)
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

export function startJdLogin(): Promise<{ started: boolean; message: string }> {
  return apiRequest('POST', '/api/v1/accounts/jd/login')
}

export function logoutJd(): Promise<Account> {
  return apiRequest<Account>('POST', '/api/v1/accounts/jd/logout')
}

export function checkJd(): Promise<Account> {
  return apiRequest<Account>('POST', '/api/v1/accounts/jd/check')
}

export function resolveListing(url: string): Promise<ListingResolve> {
  return apiRequest<ListingResolve>('POST', '/api/v1/listings/resolve', { url })
}

export function searchModel(query: string): Promise<ModelSearchResponse> {
  return apiRequest<ModelSearchResponse>('POST', '/api/v1/listings/search-model', {
    query
  })
}

export function createProduct(payload: ProductCreatePayload): Promise<ProductSummary> {
  return apiRequest<ProductSummary>('POST', '/api/v1/products', payload)
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

export function refreshProduct(productId: number): Promise<{ queued: boolean }> {
  return apiRequest('POST', `/api/v1/products/${productId}/refresh`)
}

export function verifyListing(
  listingId: number
): Promise<{ started: boolean; message: string }> {
  return apiRequest('POST', `/api/v1/listings/${listingId}/verify`)
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
