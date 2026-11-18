const HOST = 'com.pricemonitor.jd_edge'
const CAPABILITIES = ['jd', 'taobao']
const browserApi = globalThis.browser ?? globalThis.chrome
const userAgent = navigator.userAgent
const edgeBrand = navigator.userAgentData?.brands?.some((item) => item.brand === 'Microsoft Edge')
let BROWSER = 'chrome'
if (/Firefox\//.test(userAgent)) BROWSER = 'firefox'
else if (/Edg\//.test(userAgent) || edgeBrand) BROWSER = 'edge'
let port = null
let awaiting = false
let busy = false
let claimTimer = null

function setStatus(message) {
  browserApi.storage.local.set({ status: message, updatedAt: new Date().toLocaleString() })
}

function send(message) {
  if (!port || awaiting) return false
  awaiting = true
  try {
    port.postMessage(message)
    return true
  } catch (error) {
    awaiting = false
    setStatus(`通信失败：${String(error)}`)
    return false
  }
}

function connect() {
  if (port) return
  try {
    const connection = browserApi.runtime.connectNative(HOST)
    port = connection
    setStatus('已连接本机 PriceMonitor，等待京东或淘宝任务')
    connection.onMessage.addListener((reply) => {
      awaiting = false
      if (reply.error) {
        setStatus(`本机通信：${reply.error}`)
        return
      }
      if (reply.job && !busy) {
        busy = true
        runJob(reply.job).finally(() => { busy = false })
      }
    })
    connection.onDisconnect.addListener(() => {
      const error = browserApi.runtime.lastError?.message || '连接已断开'
      if (port === connection) port = null
      awaiting = false
      setStatus(`未连接 PriceMonitor：${error}`)
    })
    if (claimTimer) clearInterval(claimTimer)
    claimTimer = setInterval(() => {
      if (port && !busy && !awaiting) send({ action: 'claim', browser: BROWSER, capabilities: CAPABILITIES, protocol_version: 2 })
    }, 5000)
    send({ action: 'claim', browser: BROWSER, capabilities: CAPABILITIES, protocol_version: 2 })
  } catch (error) {
    setStatus(`无法启动本机通信：${String(error)}`)
  }
}

async function waitForComplete(tabId) {
  for (let i = 0; i < 45; i++) {
    const tab = await browserApi.tabs.get(tabId)
    if (tab.status === 'complete') return
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
  throw new Error('商品页加载超时')
}

async function openIsolatedJobWindow(job) {
  const marker = job.bootstrap_token
    ? `capture-${job.bootstrap_token}.html` : null
  if (marker) {
    // The browser can connect its extension before the command-line startup
    // tab is visible to tabs.query(). Wait for that exact local marker instead
    // of creating another window and leaving the first one behind.
    for (let attempt = 0; attempt < 30; attempt++) {
      const tabs = await browserApi.tabs.query({})
      const bootstrap = tabs.find((tab) => Number.isInteger(tab.id)
        && Number.isInteger(tab.windowId) && (tab.url || '').includes(marker))
      if (bootstrap) {
        await browserApi.tabs.update(bootstrap.id, { url: job.url, active: true })
        return { tabId: bootstrap.id, windowId: bootstrap.windowId }
      }
      await new Promise((resolve) => setTimeout(resolve, 250))
    }
    throw new Error('未找到软件启动的独立采价窗口；已取消本轮，避免打开重复窗口')
  }

  const created = await browserApi.windows.create({
    url: job.url, type: 'normal', focused: false, state: 'minimized'
  })
  if (!Number.isInteger(created?.id)) throw new Error('无法创建独立采价窗口')
  let tab = created.tabs?.find((item) => Number.isInteger(item.id))
  if (!tab) {
    const tabs = await browserApi.tabs.query({ windowId: created.id })
    tab = tabs.find((item) => Number.isInteger(item.id))
  }
  if (!Number.isInteger(tab?.id)) {
    try { await browserApi.windows.remove(created.id) } catch { /* window may close */ }
    throw new Error('独立采价窗口没有可用标签')
  }
  return { tabId: tab.id, windowId: created.id }
}

function taobaoItemKey(url) {
  try {
    const parsed = new URL(url)
    if (!['item.taobao.com', 'detail.tmall.com'].includes(parsed.hostname)
      || parsed.pathname !== '/item.htm') return null
    const itemId = parsed.searchParams.get('id')
    if (!/^\d{5,}$/.test(itemId || '')) return null
    return itemId
  } catch { return null }
}

function collectPage(job) {
  const selectText = (selectors) => {
    const found = new Set()
    for (const selector of selectors) {
      for (const node of document.querySelectorAll(selector)) {
        const value = (node.innerText || node.textContent || '').trim()
        if (value && value.length < 500) found.add(value)
        if (found.size >= 100) return [...found]
      }
    }
    return [...found]
  }

  const isTaobao = job.platform === 'taobao'
  let primaryText = ''
  let primaryPriceTexts = []
  if (!isTaobao) {
    // JD pages also render recommendations, whose "到手价" must never be
    // interpreted as the monitored SKU's price.
    const scopes = [
      '#itemInfo', '.itemInfo-wrap', '#product-intro', '.product-intro',
      '#summary', '.summary'
    ]
    for (const selector of scopes) {
      const node = document.querySelector(selector)
      const value = (node?.innerText || '').trim()
      if (value.length >= 30 && value.length <= 20000 && /[¥￥]\s*[\d,]+/.test(value)) {
        primaryText = value.slice(0, 20000)
        primaryPriceTexts = [...node.querySelectorAll(
          '#jd-price, .p-price .price, .summary-price .price, .price .price'
        )].map((price) => (price.innerText || price.textContent || '').trim())
          .filter(Boolean).slice(0, 30)
        break
      }
    }
  }
  const scriptPieces = []
  if (isTaobao) {
    const context = window.__ICE_APP_CONTEXT__
    const skuId = job.sku_id
    if (context && typeof context === 'object' && skuId) {
      const seen = new WeakSet()
      const findEntry = (value, depth = 0) => {
        if (!value || typeof value !== 'object' || depth > 16 || seen.has(value)) return null
        seen.add(value)
        if (value.sku2info && value.sku2info[skuId]) return value.sku2info[skuId]
        for (const child of Object.values(value)) {
          const found = findEntry(child, depth + 1)
          if (found) return found
        }
        return null
      }
      const entry = findEntry(context)
      if (entry) {
        const compact = { loaderData: { sku2info: { [skuId]: entry } } }
        scriptPieces.push(`<script id="__ICE_APP_CONTEXT__">${JSON.stringify(compact)}</script>`)
      }
    }
    for (const script of document.scripts) {
      const value = script.textContent || ''
      if (script.id === '__ICE_APP_CONTEXT__' || value.includes('window.__ICE_APP_CONTEXT__')) {
        scriptPieces.push(script.outerHTML.slice(0, 620000))
        break
      }
    }
  } else {
    for (const script of document.scripts) {
      const value = script.textContent || ''
      for (const needle of ['priceFloor', 'jdPrice', 'promotionPrice', 'finalPrice']) {
        const offset = value.indexOf(needle)
        if (offset >= 0) scriptPieces.push(value.slice(Math.max(0, offset - 100), offset + 30000))
      }
    }
  }

  const shopTexts = selectText(isTaobao
    ? ['.slogo-shopname', '.shop-name', 'a[href*="shop"]', '[class*="ShopName"]', '[class*="shopName"]']
    : ['#popbox a[href*="mall.jd.com"]', '#shopInfo a[href*="mall.jd.com"]',
      'a[href*="mall.jd.com"]', 'a[href*="shop.jd.com"]', '.shopName',
      '.J-hove-wrap .name', '#popbox .mt .name', '[class*="shop-name"]',
      '[class*="shopName"]'])

  return {
    url: location.href,
    visibility_state: document.visibilityState || 'unknown',
    title: document.title.slice(0, 1024),
    title_texts: isTaobao
      ? selectText(['h1', '.tb-main-title', '[class*="ItemTitle"]', '[class*="itemTitle"]', '[class*="mainTitle"]'])
      : selectText(['#name h1', '.sku-name', '.sku-title', '#itemInfo h1']),
    body: (document.body?.innerText || '').slice(0, 120000),
    primary_text: primaryText,
    primary_price_texts: primaryPriceTexts,
    price_texts: selectText(isTaobao
      ? ['.tm-price', '.tm-promo-price', '[class*="Price"]', '[class*="price"]']
      : ['#jd-price', '.p-price .price', '.summary-price .price', '.price .price', '[class*="price"]']),
    shop_texts: shopTexts,
    coupon_texts: selectText(isTaobao
      ? ['[class*="coupon"]', '[class*="Coupon"]', '[class*="quan"]']
      : ['[class*="coupon"]', '[class*="quan"]', '.quan-item', '.coupon-item']),
    html: scriptPieces.join('\n').slice(0, 650000)
  }
}

function validJob(job) {
  try {
    if (job.kind !== 'product') return false
    const url = new URL(job.url)
    if (url.protocol !== 'https:') return false
    if (job.platform === 'jd') {
      return url.hostname === 'item.jd.com' && /^\/\d+\.html$/.test(url.pathname)
    }
    if (job.platform === 'taobao') {
      return ['item.taobao.com', 'detail.tmall.com'].includes(url.hostname)
        && url.pathname === '/item.htm'
        && /^\d{5,}$/.test(url.searchParams.get('id') || '')
        && (!url.searchParams.has('skuId') || /^\d+$/.test(url.searchParams.get('skuId') || ''))
    }
  } catch { /* invalid URL */ }
  return false
}

async function captureJobTab(job, tabId, reusedTab) {
  let observation
  await waitForComplete(tabId)
  for (let i = 0; i < 12; i++) {
    const results = await browserApi.scripting.executeScript({
      target: { tabId },
      func: collectPage,
      args: [job],
      world: job.platform === 'taobao' ? 'MAIN' : 'ISOLATED'
    })
    observation = results[0]?.result
    if (!observation) throw new Error('商品页内容为空')
    observation.reused_tab = reusedTab
    const finalHost = new URL(observation.url).hostname
    if (job.platform === 'jd' && finalHost !== 'item.jd.com') break
    if (job.platform === 'taobao' && !['item.taobao.com', 'detail.tmall.com'].includes(finalHost)) break
    if (job.platform === 'jd' && (observation.price_texts.length || /(?:到手价|京东价|国补后价)/.test(observation.body))) break
    if (job.platform === 'taobao' && observation.body.length > 80
      && observation.price_texts.length && (observation.title_texts.length || observation.title.length >= 8)) break
    await new Promise((resolve) => setTimeout(resolve, 2000))
  }
  return observation
}

function unusableTaobaoObservation(job, observation) {
  if (!observation || taobaoItemKey(observation.url) !== taobaoItemKey(job.url)) return true
  const body = observation.body || ''
  if (body.includes('访问异常提示') || body.includes('系统检测到当前访问存在异常')) return true
  return body.length <= 80 || !observation.price_texts?.length
}

function unusableObservation(job, observation) {
  if (job.platform === 'taobao') return unusableTaobaoObservation(job, observation)
  if (!observation) return true
  try {
    if (new URL(observation.url).hostname !== 'item.jd.com') return true
  } catch { return true }
  return (observation.body || '').length <= 80
    || !(observation.price_texts?.length || /(?:到手价|京东价|国补后价)/.test(observation.body || ''))
}

async function runJob(job) {
  let windowId = null
  let observation
  try {
    if (!validJob(job)) throw new Error('无效的平台页面地址')
    setStatus('正在独立后台窗口读取商品')
    const isolated = await openIsolatedJobWindow(job)
    windowId = isolated.windowId
    observation = await captureJobTab(job, isolated.tabId, false)
    if (unusableObservation(job, observation)) {
      // Some shops defer rendering while a window is minimized. Restore the
      // isolated window behind the user's active window and try the same page.
      try {
        await browserApi.windows.update(windowId, { state: 'normal', focused: false })
        observation = await captureJobTab(job, isolated.tabId, false)
      } catch { /* return the first observation and let the parser explain it */ }
    }
    setStatus(`已读取 ${observation.url}`)
  } catch (error) {
    observation = { error: String(error).slice(0, 250) }
    setStatus(`商品读取失败：${observation.error}`)
  } finally {
    if (windowId !== null) {
      try { await browserApi.windows.remove(windowId) } catch { /* window was closed already */ }
    }
  }
  awaiting = false
  send({ action: 'result', browser: BROWSER, id: job.id, observation })
}

browserApi.runtime.onInstalled.addListener(connect)
browserApi.runtime.onStartup.addListener(connect)
browserApi.alarms.create('bridge-reconnect', { periodInMinutes: 1 })
browserApi.alarms.onAlarm.addListener(() => connect())
connect()
