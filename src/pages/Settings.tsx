import type { FormEvent, JSX } from 'react'
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Bell,
  CheckCircle2,
  Database,
  FolderOpen,
  Info,
  KeyRound,
  Loader2,
  RefreshCw,
  RotateCcw,
  Save,
  Send,
  ShieldAlert
} from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import {
  fetchNotificationStatus,
  fetchSettings,
  getAppInfo,
  saveServerchanKey,
  testNotification,
  updateSettings
} from '@/lib/api'
import type { AppSettings, NotificationChannel } from '@/lib/types'

const inputClass =
  'mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200'
const labelClass = 'text-sm font-medium text-slate-700'

export default function SettingsPage(): JSX.Element {
  const queryClient = useQueryClient()
  const settings = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
    retry: 1
  })
  const appInfo = useQuery({
    queryKey: ['app-info'],
    queryFn: getAppInfo,
    staleTime: Infinity,
    retry: false
  })
  const notificationStatus = useQuery({
    queryKey: ['notification-status'],
    queryFn: fetchNotificationStatus,
    retry: 1
  })

  const [pollInterval, setPollInterval] = useState(30)
  const [checkoutHours, setCheckoutHours] = useState(6)
  const [channel, setChannel] = useState<NotificationChannel>('serverchan')
  const [closeToTray, setCloseToTray] = useState(true)
  const [autoStart, setAutoStart] = useState(false)
  const [sendkey, setSendkey] = useState('')

  useEffect(() => {
    const data = settings.data
    if (!data) {
      return
    }
    setPollInterval(data.poll_interval_minutes)
    setCheckoutHours(data.checkout_interval_hours)
    setChannel(data.notification_channel)
    setCloseToTray(data.close_to_tray)
    setAutoStart(data.auto_start)
  }, [settings.data])

  const settingsMutation = useMutation({
    mutationFn: (patch: Partial<AppSettings>) => updateSettings(patch),
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
      void queryClient.invalidateQueries({ queryKey: ['settings'] })
    }
  })

  const saveKey = useMutation({
    mutationFn: saveServerchanKey,
    onSuccess: (data) => {
      setSendkey('')
      queryClient.setQueryData(['notification-status'], data)
      void queryClient.invalidateQueries({ queryKey: ['settings'] })
    }
  })

  const testPush = useMutation({
    mutationFn: testNotification
  })
  const openDataDir = useMutation({
    mutationFn: () => window.api.openDataDir()
  })
  const checkUpdates = useMutation({
    mutationFn: () => window.api.checkUpdates()
  })
  const restartOnboarding = useMutation({
    mutationFn: () => updateSettings({ onboarding_completed: false }),
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
      void queryClient.invalidateQueries({ queryKey: ['settings'] })
    }
  })

  const configured =
    notificationStatus.data?.serverchan_configured ??
    settings.data?.notification_configured ??
    false

  function handleSettingsSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault()
    settingsMutation.mutate({
      poll_interval_minutes: pollInterval,
      checkout_interval_hours: checkoutHours,
      notification_channel: channel,
      close_to_tray: closeToTray,
      auto_start: autoStart
    })
  }

  function handleKeySubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault()
    if (!sendkey.trim()) {
      return
    }
    saveKey.mutate(sendkey.trim())
  }

  return (
    <div>
      <PageHeader
        title="设置"
        description="设置保存在本地 SQLite；通知密钥保存在 Windows Credential Manager。"
      />

      {settings.isError ? (
        <div className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <span>
            读取设置失败：
            {settings.error instanceof Error ? settings.error.message : '未知错误'}
          </span>
          <button
            type="button"
            onClick={() => void settings.refetch()}
            className="rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-medium"
          >
            重试
          </button>
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
        <form
          onSubmit={handleSettingsSubmit}
          className="rounded-2xl border border-slate-200 bg-white p-5"
        >
          <h2 className="text-sm font-semibold text-slate-900">监测</h2>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            轮询间隔默认 30 分钟，修改后保存即重新排程。价格以页面预估价为主，自动结算已停用；如需核对实付，可在商品详情页手动校准。
          </p>

          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <label className={labelClass}>
              轮询间隔（分钟）
              <input
                type="number"
                min={10}
                max={180}
                value={pollInterval}
                onChange={(event) => setPollInterval(Number(event.target.value))}
                className={inputClass}
              />
              <span className="mt-1 block text-xs font-normal text-slate-400">10–180</span>
            </label>

            <label className={labelClass}>
              实付参考有效期（小时）
              <input
                type="number"
                min={4}
                max={12}
                value={checkoutHours}
                onChange={(event) => setCheckoutHours(Number(event.target.value))}
                className={inputClass}
              />
              <span className="mt-1 block text-xs font-normal text-slate-400">
                超过该时长会提示手动校准实付；不影响页面预估价
              </span>
            </label>
          </div>

          <label className={`${labelClass} mt-5 block`}>
            默认通知渠道
            <select
              value={channel}
              onChange={(event) => setChannel(event.target.value as NotificationChannel)}
              className={inputClass}
            >
              <option value="serverchan">ServerChan</option>
              <option value="pushplus">PushPlus（预留）</option>
            </select>
          </label>

          <div className="mt-5 space-y-3">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={closeToTray}
                onChange={(event) => setCloseToTray(event.target.checked)}
                className="h-4 w-4 rounded border-slate-300"
              />
              关闭窗口时最小化到托盘
              <span className="text-xs font-normal text-slate-400">
                （取消后关闭窗口会直接退出应用）
              </span>
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={autoStart}
                onChange={(event) => setAutoStart(event.target.checked)}
                className="h-4 w-4 rounded border-slate-300"
              />
              开机自启
              <span className="text-xs font-normal text-slate-400">
                {appInfo.data?.preferences.autoStartSupported
                  ? '（以 --hidden 启动，直接留在托盘）'
                  : '（开发模式仅保存，安装版生效）'}
              </span>
            </label>
          </div>

          <div className="mt-5 flex items-center gap-3">
            <button
              type="submit"
              disabled={settingsMutation.isPending}
              className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {settingsMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              保存设置
            </button>
            {settingsMutation.isSuccess ? (
              <span className="flex items-center gap-1 text-xs text-emerald-600">
                <CheckCircle2 className="h-3.5 w-3.5" />
                已保存
              </span>
            ) : null}
            {settingsMutation.isError ? (
              <span className="text-xs text-rose-600">
                {settingsMutation.error instanceof Error
                  ? settingsMutation.error.message
                  : '保存失败'}
              </span>
            ) : null}
          </div>
        </form>

        <div className="space-y-4">
          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Bell className="h-4 w-4" />
                ServerChan 推送
              </div>
              <span
                className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                  configured
                    ? 'bg-emerald-50 text-emerald-700'
                    : 'bg-slate-100 text-slate-500'
                }`}
              >
                {configured ? '已配置' : '未配置'}
              </span>
            </div>

            <form onSubmit={handleKeySubmit} className="mt-4">
              <label className={labelClass}>
                SendKey
                <input
                  type="password"
                  value={sendkey}
                  onChange={(event) => setSendkey(event.target.value)}
                  placeholder={configured ? '已配置，输入新 SendKey 可覆盖' : 'SCT...'}
                  className={inputClass}
                />
              </label>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  type="submit"
                  disabled={!sendkey.trim() || saveKey.isPending}
                  className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40"
                >
                  {saveKey.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <KeyRound className="h-4 w-4" />
                  )}
                  保存密钥
                </button>
                <button
                  type="button"
                  onClick={() => testPush.mutate()}
                  disabled={!configured || testPush.isPending}
                  className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                >
                  {testPush.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                  测试推送
                </button>
              </div>
            </form>

            {saveKey.isSuccess ? (
              <p className="mt-3 text-xs text-emerald-600">SendKey 已保存到本机凭据库。</p>
            ) : null}
            {saveKey.isError ? (
              <p className="mt-3 text-xs text-rose-600">
                {saveKey.error instanceof Error ? saveKey.error.message : '保存失败'}
              </p>
            ) : null}
            {testPush.isSuccess ? (
              <p className="mt-3 text-xs text-emerald-600">测试通知已发送，请查看微信。</p>
            ) : null}
            {testPush.isError ? (
              <p className="mt-3 text-xs text-rose-600">
                {testPush.error instanceof Error ? testPush.error.message : '发送失败'}
              </p>
            ) : null}

            <p className="mt-3 rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-500">
              目前 ServerChan 生效。密钥不会写入 SQLite，也不会显示在界面上。
            </p>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Database className="h-4 w-4" />
              本地数据
            </div>
            <div className="mt-3 flex items-start gap-2 text-xs text-slate-500">
              <FolderOpen className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="break-all font-mono leading-5">
                {appInfo.data?.dataDir ?? '等待后端连接'}
              </span>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => openDataDir.mutate()}
                disabled={openDataDir.isPending}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                {openDataDir.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <FolderOpen className="h-3.5 w-3.5" />
                )}
                打开数据目录
              </button>
              {openDataDir.data?.error ? (
                <span className="text-xs text-rose-600">{openDataDir.data.error}</span>
              ) : null}
            </div>
            <p className="mt-3 text-xs leading-5 text-slate-500">
              SQLite、日志、浏览器登录态和临时文件都在这个目录；卸载默认保留。
            </p>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Info className="h-4 w-4" />
              关于与免责声明
            </div>
            <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
              <span>PriceMonitor</span>
              <span className="font-mono">v{appInfo.data?.version ?? '0.1.0'}</span>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => restartOnboarding.mutate()}
                disabled={restartOnboarding.isPending}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                {restartOnboarding.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RotateCcw className="h-3.5 w-3.5" />
                )}
                重新查看使用向导
              </button>
              <button
                type="button"
                onClick={() => checkUpdates.mutate()}
                disabled={checkUpdates.isPending}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                {checkUpdates.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5" />
                )}
                检查更新
              </button>
            </div>
            {checkUpdates.data ? (
              <div className="mt-2 text-xs leading-5">
                {checkUpdates.data.status === 'available' ? (
                  <div className="flex flex-wrap items-center gap-2 text-emerald-700">
                    <span>发现新版本 v{checkUpdates.data.latestVersion}</span>
                    {checkUpdates.data.url ? (
                      <button
                        type="button"
                        onClick={() => {
                          const url = checkUpdates.data?.url
                          if (url) {
                            window.open(url, '_blank')
                          }
                        }}
                        className="font-medium underline underline-offset-2"
                      >
                        下载更新
                      </button>
                    ) : null}
                  </div>
                ) : null}
                {checkUpdates.data.status === 'up-to-date' ? (
                  <span className="text-slate-500">
                    已是最新版本 v{checkUpdates.data.currentVersion}
                  </span>
                ) : null}
                {checkUpdates.data.status === 'unconfigured' ? (
                  <span className="text-slate-400">
                    当前版本 v{checkUpdates.data.currentVersion} · 尚未配置发布更新源
                  </span>
                ) : null}
                {checkUpdates.data.status === 'error' ? (
                  <span className="text-rose-600">{checkUpdates.data.message ?? '检查更新失败'}</span>
                ) : null}
              </div>
            ) : null}
            {restartOnboarding.isError ? (
              <p className="mt-2 text-xs text-rose-600">
                {restartOnboarding.error instanceof Error
                  ? restartOnboarding.error.message
                  : '无法打开向导'}
              </p>
            ) : null}
            <div className="mt-3 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-800">
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
              <p>
                本项目仅供个人学习与自用比价，不保证价格准确性。自动化访问电商平台可能违反平台用户协议并带来账号风险，请自行承担。应用不包含验证码绕过、自动下单、自动支付或个人微信机器人。
              </p>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
