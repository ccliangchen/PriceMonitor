import type { FormEvent, JSX } from 'react'
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, Database, FolderOpen, Save } from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { apiRequest, getAppInfo } from '@/lib/api'
import type { AppSettings, NotificationChannel } from '@/lib/types'

const inputClass =
  'mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200'
const labelClass = 'text-sm font-medium text-slate-700'

export default function SettingsPage(): JSX.Element {
  const queryClient = useQueryClient()
  const settings = useQuery({
    queryKey: ['settings'],
    queryFn: () => apiRequest<AppSettings>('GET', '/api/v1/settings'),
    retry: 1
  })
  const appInfo = useQuery({
    queryKey: ['app-info'],
    queryFn: getAppInfo,
    staleTime: Infinity,
    retry: false
  })

  const [pollInterval, setPollInterval] = useState(30)
  const [checkoutHours, setCheckoutHours] = useState(6)
  const [channel, setChannel] = useState<NotificationChannel>('serverchan')
  const [closeToTray, setCloseToTray] = useState(true)
  const [autoStart, setAutoStart] = useState(false)

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

  const mutation = useMutation({
    mutationFn: (patch: Partial<AppSettings>) =>
      apiRequest<AppSettings>('PATCH', '/api/v1/settings', patch),
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
    }
  })

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault()
    mutation.mutate({
      poll_interval_minutes: pollInterval,
      checkout_interval_hours: checkoutHours,
      notification_channel: channel,
      close_to_tray: closeToTray,
      auto_start: autoStart
    })
  }

  return (
    <div>
      <PageHeader
        title="设置"
        description="设置保存在本地 SQLite；通知密钥后续放入 Windows Credential Manager。"
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

      <form onSubmit={handleSubmit} className="grid gap-6 lg:grid-cols-[1.25fr_1fr]">
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-slate-900">监测</h2>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            轮询间隔默认 30 分钟；结算校准只在页面价变化或达到间隔时触发，只预览不下单。
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
              结算校准间隔（小时）
              <input
                type="number"
                min={4}
                max={12}
                value={checkoutHours}
                onChange={(event) => setCheckoutHours(Number(event.target.value))}
                className={inputClass}
              />
              <span className="mt-1 block text-xs font-normal text-slate-400">4–12</span>
            </label>
          </div>

          <div className="mt-5 space-y-3">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={closeToTray}
                onChange={(event) => setCloseToTray(event.target.checked)}
                className="h-4 w-4 rounded border-slate-300"
              />
              关闭窗口时最小化到托盘（M3 接入开关）
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={autoStart}
                onChange={(event) => setAutoStart(event.target.checked)}
                className="h-4 w-4 rounded border-slate-300"
              />
              开机自启（M3 接入 Electron 启动项）
            </label>
          </div>

          <button
            type="submit"
            disabled={mutation.isPending}
            className="mt-5 inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {mutation.isPending ? '保存中…' : '保存设置'}
          </button>

          {mutation.isSuccess ? (
            <span className="ml-3 text-xs text-emerald-600">已保存</span>
          ) : null}
          {mutation.isError ? (
            <span className="ml-3 text-xs text-rose-600">
              {mutation.error instanceof Error ? mutation.error.message : '保存失败'}
            </span>
          ) : null}
        </section>

        <div className="space-y-4">
          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Bell className="h-4 w-4" />
              通知
            </div>
            <label className={`${labelClass} mt-4 block`}>
              默认渠道
              <select
                value={channel}
                onChange={(event) => setChannel(event.target.value as NotificationChannel)}
                className={inputClass}
              >
                <option value="serverchan">Server酱</option>
                <option value="pushplus">PushPlus</option>
              </select>
            </label>
            <p className="mt-3 rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-500">
              SendKey / Token 的录入和测试按钮在 M1 通知模块完成后开放，密钥会存进 Windows Credential Manager。
            </p>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Database className="h-4 w-4" />
              本地数据
            </div>
            <div className="mt-3 space-y-3 text-xs text-slate-500">
              <div className="flex items-start gap-2">
                <FolderOpen className="mt-0.5 h-4 w-4 shrink-0" />
                <span className="break-all font-mono leading-5">
                  {appInfo.data?.dataDir ?? '等待后端连接'}
                </span>
              </div>
              <p className="leading-5">
                所有数据保存在本机，不上传云端。卸载默认保留数据目录；后续设置页会提供备份与导出。
              </p>
            </div>
          </section>
        </div>
      </form>
    </div>
  )
}
