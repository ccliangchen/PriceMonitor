#!/usr/bin/env node
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const backendDir = join(root, 'backend')
const specFile = join('packaging', 'price-monitor-backend.spec')

const preferred = [
  process.env.PRICE_MONITOR_PYTHON,
  'D:\\Anaconda\\envs\\pricemonitor\\python.exe'
]
  .filter(Boolean)
  .map((candidate) => resolve(candidate))

const python =
  preferred.find((candidate) => existsSync(candidate)) ?? (process.platform === 'win32' ? 'python' : 'python3')

console.log(`[build-backend] using Python: ${python}`)

const result = spawnSync(
  python,
  ['-m', 'PyInstaller', '--noconfirm', '--clean', specFile],
  {
    cwd: backendDir,
    stdio: 'inherit',
    env: {
      ...process.env,
      PYTHONUTF8: '1',
      PYTHONIOENCODING: 'utf-8'
    }
  }
)

if (result.error) {
  console.error(`[build-backend] failed to launch Python: ${result.error.message}`)
  process.exit(1)
}
if (result.status !== 0) {
  console.error(`[build-backend] PyInstaller exited with code ${result.status}`)
  process.exit(result.status ?? 1)
}

const exePath = join(
  backendDir,
  'dist',
  'price-monitor-backend',
  process.platform === 'win32' ? 'price-monitor-backend.exe' : 'price-monitor-backend'
)
if (!existsSync(exePath)) {
  console.error(`[build-backend] expected executable not found: ${exePath}`)
  process.exit(1)
}
console.log(`[build-backend] done: ${exePath}`)
