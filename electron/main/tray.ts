import { app, Menu, Tray, nativeImage, type BrowserWindow } from 'electron'

import { resourcePath } from './paths'

let tray: Tray | null = null

export function createTray(
  getWindow: () => BrowserWindow | null,
  openSettings: () => void
): Tray {
  const icon = nativeImage.createFromPath(resourcePath('tray.png'))
  tray = new Tray(icon.isEmpty() ? nativeImage.createEmpty() : icon)
  tray.setToolTip('PriceMonitor — 价格监测')

  const showWindow = (): void => {
    const window = getWindow()
    window?.show()
    window?.focus()
  }

  const menu = Menu.buildFromTemplate([
    { label: '打开主窗口', click: showWindow },
    { label: '打开设置', click: openSettings },
    { type: 'separator' },
    { label: '退出', click: () => app.quit() }
  ])
  tray.setContextMenu(menu)
  tray.on('double-click', showWindow)
  return tray
}

export function destroyTray(): void {
  tray?.destroy()
  tray = null
}
