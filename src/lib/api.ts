import type { ApiResponse, AppInfo } from '@/types/global'

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
