import { contextBridge, ipcRenderer } from 'electron'

interface ApiResponse {
  ok: boolean
  status: number
  data?: unknown
  error?: string
}

interface DesktopPreferences {
  autoStart: boolean
  closeToTray: boolean
}

interface DesktopPreferencesState extends DesktopPreferences {
  autoStartSupported: boolean
  autoStartRegistered: boolean
}

interface AppInfo {
  version: string
  platform: string
  isDev: boolean
  dataDir: string
  preferences: DesktopPreferencesState
}

interface UpdateCheckResult {
  status: 'unconfigured' | 'up-to-date' | 'available' | 'error'
  currentVersion: string
  latestVersion?: string
  url?: string
  notes?: string
  message?: string
}

let navigateHandler: ((path: string) => void) | null = null
ipcRenderer.on('app:navigate', (_event, path: string) => {
  navigateHandler?.(String(path))
})

const api = {
  request: (method: string, path: string, body?: unknown): Promise<ApiResponse> =>
    ipcRenderer.invoke('api:request', { method, path, body }),
  getAppInfo: (): Promise<AppInfo> => ipcRenderer.invoke('app:info'),
  applyPreferences: (
    preferences: Partial<DesktopPreferences>
  ): Promise<DesktopPreferencesState> =>
    ipcRenderer.invoke('app:apply-preferences', preferences),
  getPreferences: (): Promise<DesktopPreferencesState> =>
    ipcRenderer.invoke('app:preferences'),
  openDataDir: (): Promise<{ opened: boolean; error: string | null }> =>
    ipcRenderer.invoke('app:open-data-dir'),
  checkUpdates: (): Promise<UpdateCheckResult> =>
    ipcRenderer.invoke('app:check-updates'),
  onNavigate: (callback: (path: string) => void): void => {
    navigateHandler = callback
  },
  quit: (): Promise<void> => ipcRenderer.invoke('app:quit'),
  showWindow: (): Promise<void> => ipcRenderer.invoke('window:show'),
  hideWindow: (): Promise<void> => ipcRenderer.invoke('window:hide')
}

contextBridge.exposeInMainWorld('api', api)
