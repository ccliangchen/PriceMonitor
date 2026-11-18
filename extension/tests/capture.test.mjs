import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import vm from 'node:vm'
import { fileURLToPath } from 'node:url'

const testDir = path.dirname(fileURLToPath(import.meta.url))

function loadExtension(document = {}, location = { href: 'about:blank' }) {
  const messages = []
  const port = {
    postMessage(message) { messages.push(message) },
    onMessage: { addListener() {} },
    onDisconnect: { addListener() {} }
  }
  const browser = {
    storage: { local: { set() {} } },
    runtime: {
      connectNative() { return port },
      onInstalled: { addListener() {} },
      onStartup: { addListener() {} }
    },
    alarms: { create() {}, onAlarm: { addListener() {} } }
  }
  const context = vm.createContext({
    browser, messages, navigator: { userAgent: 'Firefox/128' },
    document, location, window: {}, URL, Date,
    setTimeout(callback) { callback(); return 1 },
    setInterval() { return 1 }, clearInterval() {}
  })
  vm.runInContext(fs.readFileSync(path.join(testDir, '..', 'background.js'), 'utf8'), context)
  return context
}

test('extension accepts product pages and rejects removed search jobs', () => {
  const context = loadExtension()
  assert.equal(vm.runInContext('validJob({platform:"jd",kind:"product",url:"https://item.jd.com/123456789.html"})', context), true)
  assert.equal(vm.runInContext('validJob({platform:"taobao",kind:"product",url:"https://detail.tmall.com/item.htm?id=1234567890"})', context), true)
  assert.equal(vm.runInContext('validJob({platform:"jd",kind:"search",url:"https://search.jd.com/Search?keyword=iqoo"})', context), false)
  assert.equal(vm.runInContext('validJob({platform:"taobao",kind:"inspect",url:"https://detail.tmall.com/item.htm?id=1234567890"})', context), false)
})

test('product capture keeps the selected SKU price and seller', () => {
  const document = {
    title: 'iQOO 手机',
    body: { innerText: 'iQOO 手机 到手价 ￥3999 iQOO京东自营旗舰店' },
    scripts: [],
    querySelector() { return null },
    querySelectorAll(selector) {
      if (selector === '#jd-price') return [{ innerText: '3999' }]
      if (selector === 'a[href*="mall.jd.com"]') return [{ innerText: 'iQOO京东自营旗舰店' }]
      return []
    }
  }
  const context = loadExtension(document, { href: 'https://item.jd.com/123456789.html' })
  const result = vm.runInContext('collectPage({platform:"jd",kind:"product"})', context)
  assert.equal(result.price_texts[0], '3999')
  assert.equal(result.shop_texts[0], 'iQOO京东自营旗舰店')
})

test('Taobao capture ignores user tabs and uses an isolated window', async () => {
  const context = loadExtension()
  const url = 'https://detail.tmall.com/item.htm?id=1234567890&skuId=987654321'
  const calls = { windowsCreated: 0, windowsRemoved: [], tabsRemoved: 0 }
  context.browser.windows = {
    async create(options) {
      calls.windowsCreated++
      assert.equal(options.focused, false)
      assert.equal(options.state, 'minimized')
      return { id: 4, tabs: [{ id: 18, windowId: 4 }] }
    },
    async remove(id) { calls.windowsRemoved.push(id) },
    async update() {}
  }
  context.browser.tabs = {
    async query() { return [{ id: 17, url, status: 'complete', active: true }] },
    async get() { return { status: 'complete' } },
    async remove() { calls.tabsRemoved++ }
  }
  context.browser.scripting = {
    async executeScript() {
      return [{ result: {
        url, title: '正常商品页', body: '正常商品标题 价格和详情信息'.repeat(8),
        price_texts: ['￥2999'], title_texts: ['正常商品标题']
      } }]
    }
  }
  await vm.runInContext(`runJob({id:'test',kind:'product',platform:'taobao',url:${JSON.stringify(url)},sku_id:'987654321'})`, context)
  assert.deepEqual(calls, { windowsCreated: 1, windowsRemoved: [4], tabsRemoved: 0 })
})

test('Taobao retries a minimized isolated window without focusing it', async () => {
  const context = loadExtension()
  const url = 'https://detail.tmall.com/item.htm?id=1234567890&skuId=987654321'
  const calls = { created: [], removed: [], updated: [] }
  context.browser.windows = {
    async create(options) {
      calls.created.push(options)
      return { id: 4, tabs: [{ id: 18, windowId: 4 }] }
    },
    async update(id, options) { calls.updated.push([id, options]) },
    async remove(id) { calls.removed.push(id) }
  }
  context.browser.tabs = {
    async query() { return [] },
    async get() { return { status: 'complete' } },
  }
  let captures = 0
  context.browser.scripting = {
    async executeScript() {
      captures++
      const degraded = captures === 1
      return [{ result: {
        url, title: '正常商品页',
        body: degraded ? '访问异常提示 系统检测到当前访问存在异常'.repeat(8) : '正常商品标题 价格和详情信息'.repeat(8),
        price_texts: ['￥2999'], title_texts: ['正常商品标题']
      } }]
    }
  }
  await vm.runInContext(`runJob({id:'retry',kind:'product',platform:'taobao',url:${JSON.stringify(url)},sku_id:'987654321'})`, context)
  assert.equal(calls.created.length, 1)
  assert.equal(calls.created[0].focused, false)
  assert.equal(calls.created[0].url, url)
  assert.equal(calls.updated.length, 1)
  assert.equal(calls.updated[0][0], 4)
  assert.equal(calls.updated[0][1].state, 'normal')
  assert.equal(calls.updated[0][1].focused, false)
  assert.deepEqual(calls.removed, [4])
  assert.equal(context.messages.at(-1).observation.reused_tab, false)
})

test('auto-started marker window navigates once and is closed', async () => {
  const context = loadExtension()
  const url = 'https://item.jd.com/123456789.html'
  const marker = 'file:///C:/Temp/PriceMonitorCapture/capture-token123.html'
  const calls = { updated: [], removed: [] }
  context.browser.windows = {
    async create() { throw new Error('must use bootstrap window') },
    async remove(id) { calls.removed.push(id) },
    async update() {}
  }
  context.browser.tabs = {
    async query() { return [{ id: 11, windowId: 7, url: marker }] },
    async update(id, options) { calls.updated.push([id, options]); return { id, windowId: 7 } },
    async get() { return { status: 'complete' } }
  }
  context.browser.scripting = {
    async executeScript() {
      return [{ result: {
        url, title: '京东商品', body: '京东商品详情 京东价 ￥3999'.repeat(8),
        price_texts: ['￥3999'], title_texts: ['京东商品']
      } }]
    }
  }
  await vm.runInContext(`runJob({id:'boot',kind:'product',platform:'jd',url:${JSON.stringify(url)},bootstrap_token:'token123'})`, context)
  assert.equal(calls.updated.length, 1)
  assert.equal(calls.updated[0][0], 11)
  assert.equal(calls.updated[0][1].url, url)
  assert.equal(calls.updated[0][1].active, true)
  assert.deepEqual(calls.removed, [7])
})

test('missing auto-start marker never creates a duplicate window', async () => {
  const context = loadExtension()
  const url = 'https://detail.tmall.com/item.htm?id=1234567890'
  let created = 0
  context.browser.windows = {
    async create() { created++; return { id: 9, tabs: [{ id: 19, windowId: 9 }] } },
    async remove() {}, async update() {}
  }
  context.browser.tabs = { async query() { return [] } }
  await vm.runInContext(`runJob({id:'missing',kind:'product',platform:'taobao',url:${JSON.stringify(url)},bootstrap_token:'absent'})`, context)
  assert.equal(created, 0)
  assert.match(context.messages.at(-1).observation.error, /避免打开重复窗口/)
})

