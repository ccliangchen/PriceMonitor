import { app } from 'electron'
import { join } from 'node:path'

export const isDev = !app.isPackaged

export function userDataDir(): string {
  return app.getPath('userData')
}

export function logsDir(): string {
  return join(userDataDir(), 'logs')
}

export function resourcePath(...parts: string[]): string {
  return join(app.getAppPath(), 'resources', ...parts)
}

export function backendSourceDir(): string {
  return join(app.getAppPath(), 'backend')
}

export function defaultPythonExe(): string {
  return process.env.PRICE_MONITOR_PYTHON || 'D:\\Anaconda\\envs\\pricemonitor\\python.exe'
}

export function packagedBackendExe(): string {
  return join(process.resourcesPath, 'backend', 'price-monitor-backend.exe')
}
