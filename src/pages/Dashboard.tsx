import type { JSX } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowRight,
  CheckCircle2,
  Database,
  FolderOpen,
  RefreshCw,
  Smartphone,
  type LucideIcon
} from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { StatusDot } from '@/components/StatusDot'
import { apiRequest, getAppInfo } from '@/lib/api'
import { formatUptime } from '@/lib/format'
import type { Health } from '@/lib/types'

const M0_ITEMS = [
  'Electron 窗口、托盘、单实例与关闭到托盘',
  'Python sidecar 启动、健康检查与退出清理',
  'IPC API 代理与本地 Bearer Token 鉴权',
  'SQLite 初始化与设置读写'
]

function InfoCard({
  icon: Icon,
  label,
  value,
  mono = false
}: {
  icon: LucideIcon
  label: string
  value: string
  mono?: boolean
}): JSX.Element {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-400">
        <Icon className="h-4 w-4" />
        {label}
      </div>
      <div
        className={`mt-3 text-sm text-slate-800 ${mono ? 'break-all font-mono text-xs leading-5' : 'font-medium'}`}
        title={value}
      >
        {value}
      </div>
    </section>
  )
}

export default function Dashboard(): JSX.Element {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => apiRequest<Health>('GET', '/api/v1/health'),
    refetchInterval: 5000,
    retry: 1
  })
  const appInfo = useQuery({
    queryKey: ['app-info'],
    queryFn: getAppInfo,
    staleTime: Infinity,
    retry: false
  })

  const dataDir = health.data?.data_dir ?? appInfo.data?.dataDir ?? '—'
  const dbLabel = health.data?.database === 'ok' ? 'SQLite 正常' : '等待连接'

  return (
    <div>
      <PageHeader
        title="仪表盘"
        description="M0 骨架运行状态；M1 将接入京东官方自营 / 官方旗舰店。"
      >
        <button
          type="button"
          onClick={() => void health.refetch()}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          <RefreshCw className="h-4 w-4" />
          刷新状态
        </button>
        <button
          type="button"
          disabled
          title="M1 开放"
          className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white opacity-40"
        >
          <Smartphone className="h-4 w-4" />
          添加商品
        </button>
      </PageHeader>

      {health.isError ? (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          后端未连接：
          {health.error instanceof Error ? health.error.message : '未知错误'}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-400">
            <StatusDot tone={health.isError ? 'error' : health.data ? 'ok' : 'idle'} />
            后端状态
          </div>
          <div className="mt-3 text-lg font-semibold text-slate-900">
            {health.isPending ? '连接中…' : health.isError ? '未连接' : '运行中'}
          </div>
          <div className="mt-1 text-xs text-slate-500">
            {health.data ? `已运行 ${formatUptime(health.data.uptime_seconds)}` : '等待 sidecar 就绪'}
          </div>
        </section>

        <InfoCard icon={Database} label="数据库" value={dbLabel} />
        <InfoCard icon={FolderOpen} label="数据目录" value={dataDir} mono />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[1.35fr_1fr]">
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-slate-900">M0 验收</h2>
          <ul className="mt-4 space-y-2.5 text-sm text-slate-600">
            {M0_ITEMS.map((item) => (
              <li key={item} className="flex items-start gap-2">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
          <div className="mt-5 rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-500">
            当前商品数 0。M1 会先做京东单平台：扫码登录 → 解析链接 → 校验官方店铺 → 页面价与券 →
            30 分钟轮询 → 全平台史低 → Server酱推送。
          </div>
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5 text-white">
          <div className="text-[11px] font-medium uppercase tracking-wider text-slate-400">
            下一步
          </div>
          <h2 className="mt-2 text-lg font-semibold">M1 · 京东端到端</h2>
          <p className="mt-2 text-sm leading-6 text-slate-300">
            先跑通一条完整链路：官方自营/官方旗舰店校验、页面价与可见券、价格快照、史低判定、微信推送。
          </p>
          <div className="mt-5 flex items-center gap-2 text-sm font-medium text-emerald-300">
            <ArrowRight className="h-4 w-4" />
            一条链路跑通后再扩淘宝
          </div>
        </section>
      </div>
    </div>
  )
}
