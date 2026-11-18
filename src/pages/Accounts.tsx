import type { JSX } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle2,
  Info,
  Loader2,
  LogIn,
  LogOut,
  RefreshCw,
  ShieldCheck
} from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { checkAccount, fetchAccounts, fetchEdgeStatus, fetchSettings, logoutAccount, startLogin, updateSettings } from '@/lib/api'
import { formatDateTime, statusLabel } from '@/lib/format'
import type { Account, CaptureBrowser } from '@/lib/types'

const BROWSERS: Array<{ key: CaptureBrowser; label: string }> = [
  { key: 'edge', label: 'Edge' },
  { key: 'chrome', label: 'Google Chrome' },
  { key: 'firefox', label: 'Firefox' }
]

const PLATFORMS = [
  {
    key: 'jd',
    label: '京东',
    note: '支持京东商品详情页，不限店铺类型'
  },
  {
    key: 'taobao',
    label: '淘宝 / 天猫',
    note: '支持淘宝和天猫商品详情页，不限店铺类型'
  }
] as const

function statusStyle(status: string): string {
  if (status === 'logged_in') {
    return 'bg-emerald-50 text-emerald-700'
  }
  if (status === 'logging_in') {
    return 'bg-amber-50 text-amber-700'
  }
  if (status === 'error') {
    return 'bg-rose-50 text-rose-700'
  }
  return 'bg-slate-100 text-slate-500'
}

function PlatformCard({
  platform,
  account
}: {
  platform: (typeof PLATFORMS)[number]
  account: Account | undefined
}): JSX.Element {
  const queryClient = useQueryClient()

  const login = useMutation({
    mutationFn: () => startLogin(platform.key),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    }
  })
  const logout = useMutation({
    mutationFn: () => logoutAccount(platform.key),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    }
  })
  const check = useMutation({
    mutationFn: () => checkAccount(platform.key),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    }
  })
  const switchAccount = useMutation({
    mutationFn: async () => {
      await logoutAccount(platform.key)
      return startLogin(platform.key)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    }
  })

  function handleLogout(): void {
    if (
      !window.confirm(
        `退出登录会删除本机保存的${platform.label}登录态，确定吗？`
      )
    ) {
      return
    }
    logout.mutate()
  }

  const loggingIn = account?.status === 'logging_in'
  const loggedIn = account?.status === 'logged_in'

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-slate-900">{platform.label}</h2>
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusStyle(
                account?.status ?? 'needs_login'
              )}`}
            >
              {account ? statusLabel(account.status) : '加载中'}
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-500">{platform.note}</p>
          <p className="mt-2 text-xs text-slate-400">
            账号：{account?.display_name ?? '—'}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            最近登录：{formatDateTime(account?.last_login_at)}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {loggedIn ? (
            <>
              <button
                type="button"
                onClick={() => check.mutate()}
                disabled={check.isPending}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                {check.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-4 w-4" />
                )}
                检查登录
              </button>
              <button
                type="button"
                onClick={() => {
                  if (
                    window.confirm(
                      `切换账号会清除当前${platform.label}登录态并打开扫码窗口，确定吗？`
                    )
                  ) {
                    switchAccount.mutate()
                  }
                }}
                disabled={switchAccount.isPending}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                {switchAccount.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <LogIn className="h-4 w-4" />
                )}
                切换账号
              </button>
              <button
                type="button"
                onClick={handleLogout}
                disabled={logout.isPending}
                className="inline-flex items-center gap-2 rounded-lg border border-rose-200 bg-white px-3 py-2 text-sm font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-50"
              >
                {logout.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <LogOut className="h-4 w-4" />
                )}
                退出登录
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={() => check.mutate()}
                disabled={check.isPending || loggingIn}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                {check.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-4 w-4" />
                )}
                检查登录
              </button>
              <button
                type="button"
                onClick={() => login.mutate()}
                disabled={login.isPending || loggingIn}
                className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
              >
                {login.isPending || loggingIn ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <LogIn className="h-4 w-4" />
                )}
                扫码登录
              </button>
              {loggingIn ? (
                <button
                  type="button"
                  onClick={handleLogout}
                  disabled={logout.isPending}
                  className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                >
                  <LogOut className="h-4 w-4" />
                  取消登录
                </button>
              ) : null}
            </>
          )}
        </div>
      </div>

      {loggingIn ? (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          {platform.label}登录窗口已打开，请在弹出的浏览器窗口中扫码。登录成功后这里会自动变成“已登录”。
        </div>
      ) : null}

      {login.isSuccess ? (
        <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
          {login.data?.message}
        </div>
      ) : null}
      {login.isError ? (
        <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {login.error instanceof Error ? login.error.message : '启动登录失败'}
        </div>
      ) : null}
      {check.isError ? (
        <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {check.error instanceof Error ? check.error.message : '检查登录失败'}
        </div>
      ) : null}
      {logout.isError ? (
        <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {logout.error instanceof Error ? logout.error.message : '退出登录失败'}
        </div>
      ) : null}
      {switchAccount.isSuccess ? (
        <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
          {switchAccount.data?.message}
        </div>
      ) : null}
      {switchAccount.isError ? (
        <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {switchAccount.error instanceof Error
            ? switchAccount.error.message
            : '切换账号失败'}
        </div>
      ) : null}
    </section>
  )
}

export default function Accounts(): JSX.Element {
  const queryClient = useQueryClient()
  const accounts = useQuery({
    queryKey: ['accounts'],
    queryFn: fetchAccounts,
    refetchInterval: 3000
  })
  const edge = useQuery({
    queryKey: ['edge-status'],
    queryFn: fetchEdgeStatus,
    refetchInterval: 5000
  })
  const settings = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings
  })
  const switchBrowser = useMutation({
    mutationFn: (browser: CaptureBrowser) => updateSettings({ capture_browser: browser }),
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
      void queryClient.invalidateQueries({ queryKey: ['edge-status'] })
    }
  })
  const selectedBrowser = settings.data?.capture_browser ?? edge.data?.selected_browser ?? 'edge'

  return (
    <div>
      <PageHeader
        title="账号管理"
        description="同一个扩展可在 Edge、Chrome 或 Firefox 中读取京东链接与价格，并作为淘宝链接和采价的备用通道。"
      >
        <button
          type="button"
          onClick={() => void accounts.refetch()}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          <RefreshCw className="h-4 w-4" />
          刷新状态
        </button>
      </PageHeader>

      {accounts.isError ? (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          读取账号失败：
          {accounts.error instanceof Error ? accounts.error.message : '未知错误'}
        </div>
      ) : null}

      <div className="space-y-4">
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="flex items-center gap-3">
            <h2 className="text-base font-semibold text-slate-900">京东＋淘宝 · 浏览器扩展</h2>
            <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${edge.data?.connected ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
              {edge.data?.connected ? '扩展在线' : '浏览器待启动'}
            </span>
          </div>
          <p className="mt-2 text-sm text-slate-600">京东链接信息和价格都通过扩展读取；淘宝先用应用浏览器，失败时使用扩展。浏览器无需一直打开，采价时会自动启动独立后台窗口；请保持两个平台的登录状态。</p>
          <p className="mt-3 text-sm font-medium text-slate-700">选择采价浏览器（三选一，可随时切换）</p>
          <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label="采价浏览器">
            {BROWSERS.map((browser) => (
              <button
                key={browser.key}
                type="button"
                aria-pressed={selectedBrowser === browser.key}
                onClick={() => switchBrowser.mutate(browser.key)}
                disabled={switchBrowser.isPending || settings.isPending}
                className={`rounded-lg border px-3 py-2 text-sm font-medium transition disabled:opacity-50 ${
                  selectedBrowser === browser.key
                    ? 'border-slate-900 bg-slate-900 text-white'
                    : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                }`}
              >
                {browser.label}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-500">只由所选浏览器的扩展领取采价任务；切换后立即生效。采价窗口不会复用、切换或关闭用户正在使用的窗口。</p>
          {switchBrowser.isError ? (
            <p className="mt-2 text-xs text-rose-600">{switchBrowser.error instanceof Error ? switchBrowser.error.message : '切换失败'}</p>
          ) : null}
          <p className="mt-2 text-xs text-slate-500">所选浏览器当前状态：京东 {edge.data?.platforms.includes('jd') ? '扩展在线' : '等待自动启动'} · 淘宝备用 {edge.data?.platforms.includes('taobao') ? '扩展在线' : '等待自动启动'}。在线浏览器：{edge.data?.connected_browsers.length ? edge.data.connected_browsers.map((item) => BROWSERS.find((browser) => browser.key === item)?.label ?? item).join('、') : '无'}。</p>
          <p className="mt-1 text-xs text-slate-400">扩展目录：PriceMonitor 安装目录 / resources / edge-extension。Edge 打开 edge://extensions，Chrome 打开 chrome://extensions，启用开发者模式后加载解压缩扩展；Firefox 在 about:debugging 临时载入 manifest.json，常驻安装需要 Mozilla 签名。</p>
        </section>
        {PLATFORMS.map((platform) => (
          <PlatformCard
            key={platform.key}
            platform={platform}
            account={accounts.data?.find((item) => item.platform === platform.key)}
          />
        ))}
      </div>

      <div className="mt-6 flex items-start gap-3 rounded-2xl border border-sky-200 bg-sky-50 p-4 text-sm leading-6 text-sky-800">
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        <p>
          价格和优惠会随账号、地区、已领券/已领补贴状态变化。扩展采价使用所选浏览器的账号；应用内淘宝登录用于常规采价。即使三个浏览器同时运行，也只有所选浏览器领取任务。应用只读取页面当前展示的价格，不会自动领券或领取补贴。
        </p>
      </div>

      <div className="mt-4 flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-800">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
        <p>
          登录态只保存在本机浏览器配置目录；应用不保存账号密码。淘宝备用采价在直接抓取失败的同一轮运行；若扩展所在浏览器页面也受限，本轮不采用价格并等待下一轮。
        </p>
      </div>
    </div>
  )
}
