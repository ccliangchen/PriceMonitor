export interface ApiResponse {
  ok: boolean
  status: number
  data?: unknown
  error?: string
}

export interface DesktopPreferences {
  autoStart: boolean
  closeToTray: boolean
}

export interface DesktopPreferencesState extends DesktopPreferences {
  autoStartSupported: boolean
  autoStartRegistered: boolean
}

export interface AppInfo {
  version: string
  platform: string
  isDev: boolean
  dataDir: string
  preferences: DesktopPreferencesState
}

export interface UpdateCheckResult {
  status: 'unconfigured' | 'up-to-date' | 'available' | 'error'
  currentVersion: string
  latestVersion?: string
  url?: string
  notes?: string
  message?: string
}

export interface PriceMonitorApi {
  request(method: string, path: string, body?: unknown): Promise<ApiResponse>
  getAppInfo(): Promise<AppInfo>
  applyPreferences(preferences: Partial<DesktopPreferences>): Promise<DesktopPreferencesState>
  getPreferences(): Promise<DesktopPreferencesState>
  openDataDir(): Promise<{ opened: boolean; error: string | null }>
  checkUpdates(): Promise<UpdateCheckResult>
  onNavigate(callback: (path: string) => void): void
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
