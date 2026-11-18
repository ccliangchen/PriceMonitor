import { app, ipcMain, shell, type BrowserWindow } from 'electron'
import log from 'electron-log/main'

import { isDev, userDataDir } from './paths'
import { applyDesktopPreferences, desktopPreferences } from './preferences'
import type { Sidecar } from './sidecar'
import { checkForUpdates } from './updates'

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

// PUT is used by the ServerChan SendKey endpoint; keep it in sync with the
// methods exposed by the renderer API client.
const ALLOWED_METHODS = new Set(['GET', 'POST', 'PATCH', 'PUT', 'DELETE'])
const API_PREFIX = '/api/v1/'

export function registerIpc(
  sidecar: Sidecar,
  getWindow: () => BrowserWindow | null
): void {
  ipcMain.handle('api:request', async (_event, request: ApiRequest): Promise<ApiResponse> => {
    try {
      const method = String(request?.method ?? '').toUpperCase()
      const path = String(request?.path ?? '')

      if (!ALLOWED_METHODS.has(method)) {
        return { ok: false, status: 400, error: '不支持的请求方法' }
      }
      if (!path.startsWith(API_PREFIX)) {
        return { ok: false, status: 400, error: '请求路径不在允许范围内' }
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

      const response = await fetch(`${sidecar.info.baseUrl}${path}`, {
        method,
        headers,
        body,
        // Link resolution can try the app browser and then wait for the
        // selected browser extension. Its bridge has a 150-second deadline.
        signal: AbortSignal.timeout(path === '/api/v1/listings/resolve' ? 240000 : 30000)
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
      const timedOut = error instanceof Error && error.name === 'TimeoutError'
      return {
        ok: false,
        status: 0,
        error: timedOut && request?.path === '/api/v1/listings/resolve'
          ? '读取商品链接超时，浏览器扩展可能未返回页面；请检查所选浏览器和扩展状态'
          : `请求后端失败：${error instanceof Error ? error.message : String(error)}`
      }
    }
  })

  ipcMain.handle('app:info', () => ({
    version: app.getVersion(),
    platform: process.platform,
    isDev,
    dataDir: userDataDir(),
    preferences: desktopPreferences()
  }))

  ipcMain.handle('app:preferences', () => desktopPreferences())

  ipcMain.handle('app:apply-preferences', (_event, preferences: unknown) =>
    applyDesktopPreferences(preferences)
  )

  ipcMain.handle('app:open-data-dir', async () => {
    const error = await shell.openPath(userDataDir())
    return {
      opened: !error,
      error: error ? `打开数据目录失败：${error}` : null
    }
  })

  ipcMain.handle('app:check-updates', () => checkForUpdates())

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
