export interface ApiResponse {
  ok: boolean
  status: number
  data?: unknown
  error?: string
}

export interface AppInfo {
  version: string
  platform: string
  isDev: boolean
  dataDir: string
}

export interface PriceMonitorApi {
  request(method: string, path: string, body?: unknown): Promise<ApiResponse>
  getAppInfo(): Promise<AppInfo>
  quit(): Promise<void>
  showWindow(): Promise<void>
  hideWindow(): Promise<void>
}

declare global {
  interface Window {
    api: PriceMonitorApi
  }
}

export {}
