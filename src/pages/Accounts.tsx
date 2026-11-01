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
import { checkAccount, fetchAccounts, logoutAccount, startLogin } from '@/lib/api'
import { formatDateTime, statusLabel } from '@/lib/format'
import type { Account } from '@/lib/types'

const PLATFORMS = [
  {
    key: 'jd',
    label: '京东',
    note: '仅允许京东官方自营、官方旗舰店'
  },
  {
    key: 'taobao',
    label: '淘宝 / 天猫',
    note: '仅允许天猫官方旗舰店'
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
  const accounts = useQuery({
    queryKey: ['accounts'],
    queryFn: fetchAccounts,
    refetchInterval: 3000
  })

  return (
    <div>
      <PageHeader
        title="账号管理"
        description="使用自己的账号扫码登录，应用不保存账号密码。"
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
          价格和优惠会随账号、地区、已领券/已领补贴状态变化。请确认卡片中显示的“账号”和你浏览器里看到价格的账号一致；如果不一致，请退出后重新扫码登录。应用只读取页面当前展示的价格，不会自动领券或领取补贴。
        </p>
      </div>

      <div className="mt-4 flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-800">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
        <p>
          登录态只保存在本机浏览器配置目录；应用不保存账号密码，不绕过验证码。自动化访问可能触发平台风控，请自行评估账号风险。淘宝/天猫的风控比京东更严格，建议使用不常用的账号并降低刷新频率。
        </p>
      </div>
    </div>
  )
}
