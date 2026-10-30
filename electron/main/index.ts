import { app, BrowserWindow, dialog, shell } from 'electron'
import { mkdirSync } from 'node:fs'
import { join, resolve } from 'node:path'
import log from 'electron-log/main'

import { registerIpc } from './ipc'
import { isDev, logsDir, resourcePath } from './paths'
import { Sidecar } from './sidecar'
import { createTray, destroyTray } from './tray'

const DEFAULT_DATA_DIR = 'D:\\PriceMonitorData'

function configureDataDir(): void {
  const candidate = resolve(process.env.PRICE_MONITOR_DATA_DIR || DEFAULT_DATA_DIR)
  try {
    mkdirSync(candidate, { recursive: true })
    mkdirSync(join(candidate, 'crashdumps'), { recursive: true })
    mkdirSync(join(candidate, 'temp'), { recursive: true })
    app.setPath('userData', candidate)
    app.setPath('sessionData', candidate)
    app.setPath('crashDumps', join(candidate, 'crashdumps'))
    app.setPath('temp', join(candidate, 'temp'))
  } catch (error) {
    console.warn('Failed to use custom data directory; falling back to default', error)
  }
}

app.setName('PriceMonitor')
app.setAppUserModelId('com.pricemonitor.app')
configureDataDir()

let mainWindow: BrowserWindow | null = null
let sidecar: Sidecar | null = null
let isQuitting = false

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1180,
    height: 760,
    minWidth: 1024,
    minHeight: 680,
    center: true,
    show: false,
    autoHideMenuBar: true,
    icon: resourcePath('icon.png'),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  })

  mainWindow.on('ready-to-show', () => {
    if (!process.argv.includes('--hidden')) {
      mainWindow?.show()
    }
  })

  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault()
      mainWindow?.hide()
    }
  })

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) {
      void shell.openExternal(url)
    }
    return { action: 'deny' }
  })

  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (url !== mainWindow?.webContents.getURL()) {
      event.preventDefault()
    }
  })

  const rendererUrl = process.env.ELECTRON_RENDERER_URL
  if (isDev && rendererUrl) {
    void mainWindow.loadURL(rendererUrl)
  } else {
    void mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

async function bootstrap(): Promise<void> {
  mkdirSync(logsDir(), { recursive: true })
  log.transports.file.resolvePathFn = () => join(logsDir(), 'main.log')
  log.transports.file.level = 'info'
  log.initialize()

  sidecar = new Sidecar()
  registerIpc(sidecar, () => mainWindow)

  createWindow()
  createTray(() => mainWindow)

  sidecar.start().catch((error) => {
    log.error('failed to start sidecar', error)
    dialog.showErrorBox(
      '后端启动失败',
      `Python sidecar 未能启动。\n\n${error instanceof Error ? error.message : String(error)}\n\n日志目录：${logsDir()}`
    )
  })
}

const gotTheLock = app.requestSingleInstanceLock()

if (!gotTheLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (!mainWindow) {
      return
    }
    if (mainWindow.isMinimized()) {
      mainWindow.restore()
    }
    mainWindow.show()
    mainWindow.focus()
  })

  app.whenReady().then(bootstrap).catch((error) => {
    log.error('app bootstrap failed', error)
  })

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    } else {
      mainWindow?.show()
    }
  })

  app.on('window-all-closed', () => {
    // Keep running in the tray on Windows.
  })

  app.on('before-quit', (event) => {
    if (isQuitting) {
      return
    }
    event.preventDefault()
    isQuitting = true
    Promise.resolve(sidecar?.stop())
      .catch((error) => log.error('failed to stop sidecar', error))
      .finally(() => {
        destroyTray()
        app.exit(0)
      })
  })
}
