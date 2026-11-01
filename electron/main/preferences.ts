import { app, type LoginItemSettingsOptions, type Settings as LoginItemSettings } from 'electron'
import log from 'electron-log/main'

export interface DesktopPreferences {
  autoStart: boolean
  closeToTray: boolean
}

export interface DesktopPreferencesState extends DesktopPreferences {
  autoStartSupported: boolean
  autoStartRegistered: boolean
}

const state: DesktopPreferences = {
  autoStart: false,
  closeToTray: true
}

function autoStartArgs(): string[] {
  return ['--hidden']
}

function loginItemOptions(openAtLogin: boolean): LoginItemSettings {
  return {
    openAtLogin,
    path: process.execPath,
    args: autoStartArgs()
  }
}

function loginItemQuery(): LoginItemSettingsOptions {
  return {
    path: process.execPath,
    args: autoStartArgs()
  }
}

function registeredAutoStart(): boolean {
  if (!app.isPackaged) {
    return false
  }
  try {
    return app.getLoginItemSettings(loginItemQuery()).openAtLogin
  } catch (error) {
    log.warn('failed to read login item settings', error)
    return false
  }
}

export function desktopPreferences(): DesktopPreferencesState {
  return {
    ...state,
    autoStartSupported: app.isPackaged,
    autoStartRegistered: registeredAutoStart()
  }
}

export function closeToTrayEnabled(): boolean {
  return state.closeToTray
}

/**
 * Apply renderer/backend settings to the Electron shell.
 *
 * `autoStart` is only registered for packaged builds; in development the
 * executable is Electron itself, so registering it would launch the wrong app.
 */
export function applyDesktopPreferences(input: unknown): DesktopPreferencesState {
  const patch =
    input && typeof input === 'object' ? (input as Record<string, unknown>) : {}

  if (typeof patch.closeToTray === 'boolean') {
    state.closeToTray = patch.closeToTray
  }
  if (typeof patch.autoStart === 'boolean') {
    state.autoStart = patch.autoStart
    if (app.isPackaged) {
      try {
        app.setLoginItemSettings(loginItemOptions(state.autoStart))
        log.info(`auto start ${state.autoStart ? 'enabled' : 'disabled'}`)
      } catch (error) {
        log.error('failed to update login item settings', error)
      }
    } else if (state.autoStart) {
      log.info('auto start setting saved; registration is skipped in development')
    }
  }

  return desktopPreferences()
}
