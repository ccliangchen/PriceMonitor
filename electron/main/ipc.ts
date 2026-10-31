import { app, ipcMain, type BrowserWindow } from 'electron'
import log from 'electron-log/main'

import { isDev, userDataDir } from './paths'
import type { Sidecar } from './sidecar'

interface ApiRequest {
  method: string
  path: string
  body?: unknown
}

interface ApiResponse {
  ok: boolean
  status: number
  data?: unknown
  error?: string
}

const ALLOWED_METHODS = new Set(['GET', 'POST', 'PATCH', 'DELETE'])
const API_PREFIX = '/api/v1/'

export function registerIpc(
  sidecar: Sidecar,
  getWindow: () => BrowserWindow | null
): void {
  ipcMain.handle('api:request', async (_event, request: ApiRequest): Promise<ApiResponse> => {
    try {
      const method = String(request?.method ?? '').toUpperCase()
      const path = String(request?.path ?? '')

      if (!ALLOWED_METHODS.has(method) || !path.startsWith(API_PREFIX)) {
        return { ok: false, status: 400, error: 'Invalid API request' }
      }

      const headers: Record<string, string> = {
        Authorization: `Bearer ${sidecar.info.token}`,
        Accept: 'application/json'
      }
      let body: string | undefined
      if (request.body !== undefined && method !== 'GET') {
        headers['Content-Type'] = 'application/json'
        body = JSON.stringify(request.body)
      }

      const timeoutMs = path.includes('/listings/search-model') ? 120000 : 30000
      const response = await fetch(`${sidecar.info.baseUrl}${path}`, {
        method,
        headers,
        body,
        signal: AbortSignal.timeout(timeoutMs)
      })
      const text = await response.text()
      let data: unknown = null
      if (text) {
        try {
          data = JSON.parse(text)
        } catch {
          data = text
        }
      }
      return { ok: response.ok, status: response.status, data }
    } catch (error) {
      log.error('API proxy failed', error)
      return {
        ok: false,
        status: 0,
        error: error instanceof Error ? error.message : String(error)
      }
    }
  })

  ipcMain.handle('app:info', () => ({
    version: app.getVersion(),
    platform: process.platform,
    isDev,
    dataDir: userDataDir()
  }))

  ipcMain.handle('app:quit', () => {
    app.quit()
  })

  ipcMain.handle('window:show', () => {
    const window = getWindow()
    window?.show()
    window?.focus()
  })

  ipcMain.handle('window:hide', () => {
    getWindow()?.hide()
  })
}
