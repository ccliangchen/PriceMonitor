function showStatus(state) {
  document.getElementById('status').textContent = state.status || '等待连接本机 PriceMonitor'
  document.getElementById('updated').textContent = state.updatedAt || ''
}

const keys = ['status', 'updatedAt']
if (globalThis.browser) {
  globalThis.browser.storage.local.get(keys).then(showStatus)
} else {
  globalThis.chrome.storage.local.get(keys, showStatus)
}
