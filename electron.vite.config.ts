import { resolve } from 'node:path'
import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// VS Code extension hosts set this; it makes Electron run as plain Node.
delete process.env.ELECTRON_RUN_AS_NODE

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: { index: resolve('electron/main/index.ts') }
      }
    }
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: { index: resolve('electron/preload/index.ts') }
      }
    }
  },
  renderer: {
    root: resolve('src'),
    resolve: {
      alias: { '@': resolve('src') }
    },
    plugins: [react(), tailwindcss()],
    build: {
      rollupOptions: {
        input: { index: resolve('src/index.html') }
      }
    }
  }
})
