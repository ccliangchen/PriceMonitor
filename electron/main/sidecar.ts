import { spawn, execFile, type ChildProcess } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { createWriteStream, mkdirSync, writeFileSync, rmSync, type WriteStream } from 'node:fs'
import net from 'node:net'
import { join } from 'node:path'
import { app } from 'electron'
import log from 'electron-log/main'

import {
  backendSourceDir,
  defaultPythonExe,
  isDev,
  logsDir,
  packagedBackendExe,
  userDataDir
} from './paths'

export interface SidecarInfo {
  port: number
  token: string
  baseUrl: string
}

export interface ShellSettings {
  auto_start?: boolean
  close_to_tray?: boolean
}

export class Sidecar {
  private child: ChildProcess | null = null
  private port = 0
  private token = ''
  private baseUrl = ''
  private stopping = false
  private restartCount = 0
  private stdoutStream: WriteStream | null = null
  private stderrStream: WriteStream | null = null

  get info(): SidecarInfo {
    return { port: this.port, token: this.token, baseUrl: this.baseUrl }
  }

  async start(): Promise<void> {
    mkdirSync(logsDir(), { recursive: true })
    this.port = await getFreePort()
    this.token = randomBytes(32).toString('hex')
    this.baseUrl = `http://127.0.0.1:${this.port}`
    this.stopping = false
    this.spawnProcess()
    await this.waitForHealth()
    this.publishEdgeBridge()
    this.restartCount = 0
  }

  async fetchShellSettings(): Promise<ShellSettings | null> {
    if (!this.baseUrl) {
      return null
    }
    try {
      const response = await fetch(`${this.baseUrl}/api/v1/settings`, {
        headers: this.authHeaders(),
        signal: AbortSignal.timeout(3000)
      })
      if (!response.ok) {
        log.warn(`failed to read shell settings: HTTP ${response.status}`)
        return null
      }
      return (await response.json()) as ShellSettings
    } catch (error) {
      log.warn('failed to read shell settings', error)
      return null
    }
  }

  async stop(): Promise<void> {
    if (!this.child || this.stopping) {
      return
    }
    this.stopping = true

    try {
      await fetch(`${this.baseUrl}/api/v1/shutdown`, {
        method: 'POST',
        headers: this.authHeaders(),
        signal: AbortSignal.timeout(2000)
      })
    } catch (error) {
      log.warn('sidecar shutdown request failed', error)
    }

    const exited = await waitForExit(this.child, 5000)
    if (!exited && this.child?.pid) {
      if (process.platform === 'win32') {
        await new Promise<void>((resolve) => {
          execFile(
            'taskkill',
            ['/pid', String(this.child?.pid), '/T', '/F'],
            () => resolve()
          )
        })
      } else {
        this.child.kill('SIGTERM')
      }
    }

    this.child = null
    this.closeLogStreams()
    this.removeEdgeBridge()
  }

  private edgeBridgePath(): string {
    return join(app.getPath('appData'), 'PriceMonitor', 'edge-bridge.json')
  }

  private publishEdgeBridge(): void {
    const path = this.edgeBridgePath()
    mkdirSync(join(app.getPath('appData'), 'PriceMonitor'), { recursive: true })
    writeFileSync(path, JSON.stringify({ port: this.port, token: this.token }), {
      encoding: 'utf-8',
      mode: 0o600
    })
  }

  private removeEdgeBridge(): void {
    rmSync(this.edgeBridgePath(), { force: true })
  }

  private authHeaders(): Record<string, string> {
    return { Authorization: `Bearer ${this.token}` }
  }

  private spawnProcess(): void {
    const args = [
      '--port',
      String(this.port),
      '--data-dir',
      userDataDir(),
      '--log-level',
      'INFO'
    ]
    const tempDir = join(userDataDir(), 'temp')
    mkdirSync(tempDir, { recursive: true })
    const env = {
      ...process.env,
      PRICE_MONITOR_TOKEN: this.token,
      TEMP: tempDir,
      TMP: tempDir,
      PYTHONUNBUFFERED: '1',
      PYTHONIOENCODING: 'utf-8'
    }

    if (isDev) {
      this.child = spawn(defaultPythonExe(), ['-m', 'app.main', ...args], {
        cwd: backendSourceDir(),
        env,
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe']
      })
    } else {
      this.child = spawn(packagedBackendExe(), args, {
        cwd: join(process.resourcesPath, 'backend'),
        env,
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe']
      })
    }

    this.attachLogs()
    this.child.on('exit', (code, signal) => {
      this.handleExit(code, signal)
    })
    this.child.on('error', (error) => {
      log.error('sidecar spawn error', error)
    })
    log.info(`sidecar started pid=${this.child.pid} port=${this.port} dev=${isDev}`)
  }

  private attachLogs(): void {
    if (!this.child) {
      return
    }
    mkdirSync(logsDir(), { recursive: true })
    this.stdoutStream = createWriteStream(join(logsDir(), 'backend-stdout.log'), {
      flags: 'a'
    })
    this.stderrStream = createWriteStream(join(logsDir(), 'backend-stderr.log'), {
      flags: 'a'
    })
    this.child.stdout?.pipe(this.stdoutStream)
    this.child.stderr?.pipe(this.stderrStream)
    this.child.stdout?.on('data', (chunk: Buffer) => {
      log.info(`[backend] ${chunk.toString('utf-8').trimEnd()}`)
    })
    this.child.stderr?.on('data', (chunk: Buffer) => {
      log.warn(`[backend] ${chunk.toString('utf-8').trimEnd()}`)
    })
  }

  private closeLogStreams(): void {
    this.stdoutStream?.end()
    this.stderrStream?.end()
    this.stdoutStream = null
    this.stderrStream = null
  }

  private async waitForHealth(timeoutMs = 60000): Promise<void> {
    const deadline = Date.now() + timeoutMs
    let lastError: unknown = null

    while (Date.now() < deadline) {
      try {
        const response = await fetch(`${this.baseUrl}/api/v1/health`, {
          headers: this.authHeaders(),
          signal: AbortSignal.timeout(2000)
        })
        if (response.ok) {
          log.info('sidecar health check passed')
          return
        }
        lastError = new Error(`健康检查返回 HTTP ${response.status}`)
      } catch (error) {
        lastError = error
      }
      await sleep(500)
    }

    throw new Error(`后端服务未在超时时间内就绪：${String(lastError)}`)
  }

  private handleExit(code: number | null, signal: NodeJS.Signals | null): void {
    this.child = null
    this.closeLogStreams()

    if (this.stopping) {
      log.info('sidecar exited during shutdown', { code, signal })
      return
    }

    log.error('sidecar exited unexpectedly', { code, signal })
    if (this.restartCount >= 3) {
      log.error('sidecar restart limit reached; not restarting')
      this.removeEdgeBridge()
      return
    }

    this.restartCount += 1
    const delay = [2000, 5000, 10000][this.restartCount - 1] ?? 10000
    setTimeout(() => {
      if (this.stopping) {
        return
      }
      log.info(`restarting sidecar (attempt ${this.restartCount})`)
      this.spawnProcess()
      this.waitForHealth()
        .then(() => {
          this.restartCount = 0
        })
        .catch((error) => log.error('sidecar restart health check failed', error))
    }, delay)
  }
}

function getFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.unref()
    server.on('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      const port = typeof address === 'object' && address ? address.port : 0
      server.close(() => resolve(port))
    })
  })
}

function waitForExit(child: ChildProcess, timeoutMs: number): Promise<boolean> {
  return new Promise((resolve) => {
    if (child.exitCode !== null) {
      resolve(true)
      return
    }
    const timer = setTimeout(() => {
      cleanup()
      resolve(false)
    }, timeoutMs)
    const onExit = (): void => {
      cleanup()
      resolve(true)
    }
    function cleanup(): void {
      clearTimeout(timer)
      child.off('exit', onExit)
    }
    child.once('exit', onExit)
  })
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
