import { contextBridge, ipcRenderer } from 'electron'

interface ApiResponse {
  ok: boolean
  status: number
  data?: unknown
  error?: string
}

interface AppInfo {
  version: string
  platform: string
  isDev: boolean
  dataDir: string
}

const api = {
  request: (method: string, path: string, body?: unknown): Promise<ApiResponse> =>
    ipcRenderer.invoke('api:request', { method, path, body }),
  getAppInfo: (): Promise<AppInfo> => ipcRenderer.invoke('app:info'),
  quit: (): Promise<void> => ipcRenderer.invoke('app:quit'),
  showWindow: (): Promise<void> => ipcRenderer.invoke('window:show'),
  hideWindow: (): Promise<void> => ipcRenderer.invoke('window:hide')
}

contextBridge.exposeInMainWorld('api', api)
