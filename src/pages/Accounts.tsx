import type { JSX } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle2,
  Loader2,
  LogIn,
  LogOut,
  RefreshCw,
  ShieldCheck
} from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { checkJd, fetchAccounts, logoutJd, startJdLogin } from '@/lib/api'
import { formatDateTime, statusLabel } from '@/lib/format'

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

export default function Accounts(): JSX.Element {
  const queryClient = useQueryClient()
  const accounts = useQuery({
    queryKey: ['accounts'],
    queryFn: fetchAccounts,
    refetchInterval: 3000
  })
  const jd = accounts.data?.find((account) => account.platform === 'jd')

  const login = useMutation({
    mutationFn: startJdLogin,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    }
  })
  const logout = useMutation({
    mutationFn: logoutJd,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    }
  })
  const check = useMutation({
    mutationFn: checkJd,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    }
  })

  function handleLogout(): void {
    if (!window.confirm('退出登录会删除本机保存的京东登录态，确定吗？')) {
      return
    }
    logout.mutate()
  }

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

      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold text-slate-900">京东</h2>
              <span
                className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusStyle(
                  jd?.status ?? 'needs_login'
                )}`}
              >
                {jd ? statusLabel(jd.status) : '加载中'}
              </span>
            </div>
            <p className="mt-1 text-sm text-slate-500">
              仅允许京东官方自营、官方旗舰店
            </p>
            <p className="mt-2 text-xs text-slate-400">
              最近登录：{formatDateTime(jd?.last_login_at)}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {jd?.status === 'logged_in' ? (
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
                  disabled={check.isPending || jd?.status === 'logging_in'}
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
                  disabled={login.isPending || jd?.status === 'logging_in'}
                  className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
                >
                  {login.isPending || jd?.status === 'logging_in' ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <LogIn className="h-4 w-4" />
                  )}
                  扫码登录
                </button>
                {jd?.status === 'logging_in' ? (
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

        {jd?.status === 'logging_in' ? (
          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            京东登录窗口已打开，请在弹出的浏览器窗口中扫码。登录成功后这里会自动变成“已登录”。
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
      </section>

      <div className="mt-6 flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-800">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
        <p>
          登录态只保存在本机浏览器配置目录；应用不保存账号密码，不绕过验证码。自动化访问可能触发平台风控，请自行评估账号风险。
        </p>
      </div>
    </div>
  )
}
