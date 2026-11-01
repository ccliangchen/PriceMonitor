import { app } from 'electron'
import { readFileSync } from 'node:fs'
import log from 'electron-log/main'

import { resourcePath } from './paths'

export interface UpdateCheckResult {
  status: 'unconfigured' | 'up-to-date' | 'available' | 'error'
  currentVersion: string
  latestVersion?: string
  url?: string
  notes?: string
  message?: string
}

interface UpdateManifest {
  version: string
  url?: string
  notes?: string
}

function manifestUrl(): string {
  const fromEnv = (process.env.PRICE_MONITOR_UPDATE_MANIFEST_URL ?? '').trim()
  if (fromEnv) {
    return fromEnv
  }
  try {
    const config = JSON.parse(readFileSync(resourcePath('update.json'), 'utf-8')) as {
      manifest_url?: string
    }
    return (config.manifest_url ?? '').trim()
  } catch (error) {
    log.warn('failed to read update configuration', error)
    return ''
  }
}

function versionParts(version: string): number[] {
  return version
    .replace(/^v/i, '')
    .split(/[.+-]/)
    .slice(0, 3)
    .map((part) => Number.parseInt(part, 10) || 0)
}

function isNewerVersion(latest: string, current: string): boolean {
  const left = versionParts(latest)
  const right = versionParts(current)
  for (let index = 0; index < 3; index += 1) {
    const a = left[index] ?? 0
    const b = right[index] ?? 0
    if (a !== b) {
      return a > b
    }
  }
  return false
}

export async function checkForUpdates(): Promise<UpdateCheckResult> {
  const currentVersion = app.getVersion()
  const url = manifestUrl()
  if (!url) {
    return {
      status: 'unconfigured',
      currentVersion,
      message: '当前版本未配置更新清单（resources/update.json）'
    }
  }
  if (!url.startsWith('https://')) {
    return {
      status: 'error',
      currentVersion,
      message: '更新清单地址必须是 HTTPS'
    }
  }

  try {
    const response = await fetch(url, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(10000)
    })
    if (!response.ok) {
      return {
        status: 'error',
        currentVersion,
        message: `更新清单返回 HTTP ${response.status}`
      }
    }
    if (!response.url.startsWith('https://')) {
      return {
        status: 'error',
        currentVersion,
        message: '更新清单被重定向到非 HTTPS 地址'
      }
    }
    const manifest = (await response.json()) as UpdateManifest
    if (!manifest.version) {
      return {
        status: 'error',
        currentVersion,
        message: '更新清单缺少 version 字段'
      }
    }
    if (!isNewerVersion(manifest.version, currentVersion)) {
      return {
        status: 'up-to-date',
        currentVersion,
        latestVersion: manifest.version.replace(/^v/i, '')
      }
    }
    const downloadUrl = (manifest.url ?? '').trim()
    if (downloadUrl && !downloadUrl.startsWith('https://')) {
      return {
        status: 'error',
        currentVersion,
        message: '更新清单中的下载地址必须是 HTTPS'
      }
    }
    return {
      status: 'available',
      currentVersion,
      latestVersion: manifest.version.replace(/^v/i, ''),
      url: downloadUrl || undefined,
      notes: manifest.notes
    }
  } catch (error) {
    log.warn('update check failed', error)
    return {
      status: 'error',
      currentVersion,
      message: `检查更新失败：${error instanceof Error ? error.message : String(error)}`
    }
  }
}
