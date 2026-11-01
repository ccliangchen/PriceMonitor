import type { JSX } from 'react'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  ArrowRight,
  BellRing,
  Check,
  CheckCircle2,
  Loader2,
  LockKeyhole,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import {
  fetchNotificationStatus,
  saveServerchanKey,
  testNotification,
  updateSettings
} from '@/lib/api'
import type { AppSettings } from '@/lib/types'

const STEPS = ['欢迎与免责声明', '配置推送', '开始使用'] as const

const inputClass =
  'mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200'

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败，请稍后重试'
}

export function Onboarding({ onFinished }: { onFinished: () => void }): JSX.Element {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [step, setStep] = useState(0)
  const [accepted, setAccepted] = useState(false)
  const [sendkey, setSendkey] = useState('')
  const [finishing, setFinishing] = useState(false)
  const [finishError, setFinishError] = useState<string | null>(null)

  const notificationStatus = useQuery({
    queryKey: ['notification-status'],
    queryFn: fetchNotificationStatus,
    retry: 1
  })
  const saveKey = useMutation({
    mutationFn: saveServerchanKey,
    onSuccess: (data) => {
      setSendkey('')
      queryClient.setQueryData(['notification-status'], data)
    }
  })
  const testPush = useMutation({ mutationFn: testNotification })

  const configured = notificationStatus.data?.serverchan_configured ?? false

  async function finish(path?: string): Promise<void> {
    setFinishing(true)
    setFinishError(null)
    try {
      const data: AppSettings = await updateSettings({ onboarding_completed: true })
      queryClient.setQueryData(['settings'], data)
      onFinished()
      if (path) {
        navigate(path)
      }
    } catch (error) {
      setFinishError(errorMessage(error))
    } finally {
      setFinishing(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="onboarding-title"
    >
      <section className="flex max-h-[calc(100vh-1.5rem)] w-full max-w-2xl flex-col overflow-hidden rounded-3xl border border-white/10 bg-white shadow-2xl">
        <div className="shrink-0 border-b border-slate-100 bg-slate-50/80 px-7 py-6">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-900 text-lg font-bold text-white">
              ¥
            </div>
            <div>
              <h1 id="onboarding-title" className="text-lg font-semibold text-slate-900">
                欢迎使用 PriceMonitor
              </h1>
              <p className="mt-0.5 text-xs text-slate-500">
                京东 / 淘宝官方店铺价格监测 · 本地运行 · 数据不上传
              </p>
            </div>
          </div>
          <ol className="mt-5 flex items-center gap-2 text-[11px]">
            {STEPS.map((label, index) => (
              <li key={label} className="flex flex-1 items-center gap-2">
                <span
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full font-semibold ${
                    index < step
                      ? 'bg-emerald-500 text-white'
                      : index === step
                        ? 'bg-slate-900 text-white'
                        : 'bg-slate-200 text-slate-500'
                  }`}
                >
                  {index < step ? <Check className="h-3 w-3" /> : index + 1}
                </span>
                <span
                  className={index === step ? 'font-medium text-slate-800' : 'text-slate-400'}
                >
                  {label}
                </span>
              </li>
            ))}
          </ol>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-7 py-6">
          {step === 0 ? (
            <div>
              <div className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-slate-700" />
                <div className="text-sm leading-6 text-slate-700">
                  <p className="font-medium text-slate-900">它能做什么</p>
                  <ul className="mt-2 space-y-1.5 text-slate-600">
                    <li>· 每 30 分钟抓取京东、淘宝/天猫官方店铺的页面预估价</li>
                    <li>· 同一商品跨平台比价，只推送全平台新低</li>
                    <li>· 史低、价格曲线、任务日志全部保存在本机</li>
                  </ul>
                </div>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                {[
                  { icon: ShieldCheck, title: '仅官方店铺', text: '官方旗舰店 / 京东官方自营' },
                  { icon: LockKeyhole, title: '不保存密码', text: '只保留本机登录态' },
                  { icon: ShieldAlert, title: '不自动下单', text: '只读取价格，不提交订单' }
                ].map(({ icon: Icon, title, text }) => (
                  <div key={title} className="rounded-xl border border-slate-200 p-3">
                    <Icon className="h-4 w-4 text-slate-500" />
                    <div className="mt-2 text-xs font-semibold text-slate-800">{title}</div>
                    <div className="mt-1 text-[11px] leading-4 text-slate-500">{text}</div>
                  </div>
                ))}
              </div>

              <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
                <p className="font-semibold">免责声明与账号风险</p>
                <p className="mt-1 text-xs leading-5 text-amber-800">
                  本项目仅供个人学习与自用比价，不保证价格完全准确。自动化访问电商平台可能违反平台用户协议并带来账号风控风险，请自行评估并承担。应用不提供验证码绕过、自动下单、自动支付、个人微信机器人等功能；建议使用不常用的账号，并保持较低的轮询频率。
                </p>
              </div>

              <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 p-3 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={accepted}
                  onChange={(event) => setAccepted(event.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-slate-300"
                />
                <span>我已阅读并理解上述免责声明，自愿承担使用自动化工具可能带来的账号风险。</span>
              </label>

            </div>
          ) : null}

          {step === 1 ? (
            <div>
              <div className="flex items-start gap-3">
                <div className="rounded-xl bg-slate-100 p-2">
                  <BellRing className="h-5 w-5 text-slate-700" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-slate-900">配置微信推送（可选）</h2>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    推荐使用 ServerChan：在 ServerChan 官网获取 SendKey，填到下面即可。密钥保存在 Windows
                    凭据管理器，不会写入数据库。
                  </p>
                </div>
              </div>

              <div className="mt-4 rounded-2xl border border-slate-200 p-4">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-medium text-slate-600">ServerChan 状态</span>
                  <span
                    className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                      configured ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    {configured ? '已配置' : '未配置'}
                  </span>
                </div>

                <form
                  className="mt-3"
                  onSubmit={(event) => {
                    event.preventDefault()
                    if (sendkey.trim()) {
                      saveKey.mutate(sendkey.trim())
                    }
                  }}
                >
                  <input
                    type="password"
                    value={sendkey}
                    onChange={(event) => setSendkey(event.target.value)}
                    placeholder={configured ? '已配置，输入新 SendKey 可覆盖' : 'SCT...'}
                    className={inputClass}
                  />
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <button
                      type="submit"
                      disabled={!sendkey.trim() || saveKey.isPending}
                      className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40"
                    >
                      {saveKey.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <CheckCircle2 className="h-4 w-4" />
                      )}
                      保存 SendKey
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
                      发送测试通知
                    </button>
                  </div>
                </form>

                {saveKey.isError ? (
                  <p className="mt-3 text-xs text-rose-600">{errorMessage(saveKey.error)}</p>
                ) : null}
                {saveKey.isSuccess ? (
                  <p className="mt-3 text-xs text-emerald-600">SendKey 已保存。</p>
                ) : null}
                {testPush.isSuccess ? (
                  <p className="mt-3 text-xs text-emerald-600">测试通知已发送，请查看微信。</p>
                ) : null}
                {testPush.isError ? (
                  <p className="mt-3 text-xs text-rose-600">{errorMessage(testPush.error)}</p>
                ) : null}
              </div>

              <p className="mt-3 text-xs leading-5 text-slate-400">
                先跳过也可以，之后随时在“设置 → ServerChan 推送”里配置。
              </p>

            </div>
          ) : null}

          {step === 2 ? (
            <div>
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-emerald-900">
                  <CheckCircle2 className="h-4 w-4" />
                  准备完成
                </div>
                <p className="mt-1 text-xs leading-5 text-emerald-800">
                  接下来先登录京东 / 淘宝账号，再按型号搜索或粘贴商品链接。应用只允许官方旗舰店和京东官方自营，校验通过后才会开始监测。
                </p>
              </div>

              <div className="mt-4 space-y-2 text-sm text-slate-600">
                <div className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2.5">
                  <Check className="h-4 w-4 text-emerald-500" />
                  价格以页面预估价为主，低置信度数据不会写入史低或推送
                </div>
                <div className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2.5">
                  <Check className="h-4 w-4 text-emerald-500" />
                  关闭窗口默认留在托盘继续监测，可在设置中改为直接退出
                </div>
                <div className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2.5">
                  <Check className="h-4 w-4 text-emerald-500" />
                  开机自启可在设置中开启（安装版生效）
                </div>
              </div>

              <p className="mt-4 text-center text-[11px] text-slate-400">
                之后可在“设置 → 关于”里重新打开本向导。
              </p>
            </div>
          ) : null}
        </div>

        <footer className="shrink-0 border-t border-slate-100 bg-white px-7 py-4">
          {step === 0 ? (
            <div className="flex items-center justify-between gap-3">
              <span className="text-[11px] text-slate-400">勾选免责声明后可继续</span>
              <button
                type="button"
                disabled={!accepted}
                onClick={() => setStep(1)}
                className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
              >
                下一步
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          ) : null}

          {step === 1 ? (
            <div className="flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => setStep(0)}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
              >
                <ArrowLeft className="h-4 w-4" />
                上一步
              </button>
              <button
                type="button"
                onClick={() => setStep(2)}
                className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
              >
                {configured ? '下一步' : '暂不配置，继续'}
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          ) : null}

          {step === 2 ? (
            <div>
              {finishError ? (
                <p className="mb-3 rounded-lg border border-rose-200 bg-rose-50 p-2.5 text-xs text-rose-700">
                  {finishError}
                </p>
              ) : null}
              <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  disabled={finishing}
                  onClick={() => void finish('/accounts')}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  先登录账号
                </button>
                <button
                  type="button"
                  disabled={finishing}
                  onClick={() => void finish('/add')}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  添加第一个商品
                </button>
                <button
                  type="button"
                  disabled={finishing}
                  onClick={() => void finish('/')}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
                >
                  {finishing ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <CheckCircle2 className="h-4 w-4" />
                  )}
                  进入仪表盘
                </button>
              </div>
            </div>
          ) : null}
        </footer>
      </section>
    </div>
  )
}
