import type { JSX } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Plus, RefreshCw, ShieldCheck, Smartphone } from 'lucide-react'
import { Link } from 'react-router-dom'

import { PageHeader } from '@/components/PageHeader'
import { ProductCard } from '@/components/ProductCard'
import { StatusDot } from '@/components/StatusDot'
import {
  fetchAccounts,
  fetchHealth,
  fetchProducts,
  fetchSettings,
  getAppInfo
} from '@/lib/api'
import { statusLabel } from '@/lib/format'

function StatCard({
  label,
  value,
  hint
}: {
  label: string
  value: string
  hint?: string
}): JSX.Element {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="text-xs font-medium uppercase tracking-wider text-slate-400">{label}</div>
      <div className="mt-2 text-lg font-semibold text-slate-900">{value}</div>
      {hint ? <div className="mt-1 text-xs text-slate-500">{hint}</div> : null}
    </section>
  )
}

export default function Dashboard(): JSX.Element {
  const products = useQuery({
    queryKey: ['products'],
    queryFn: fetchProducts,
    refetchInterval: 10000
  })
  const health = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 10000
  })
  const settings = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings
  })
  const accounts = useQuery({
    queryKey: ['accounts'],
    queryFn: fetchAccounts,
    refetchInterval: 10000
  })
  const appInfo = useQuery({
    queryKey: ['app-info'],
    queryFn: getAppInfo,
    staleTime: Infinity,
    retry: false
  })

  const jd = accounts.data?.find((account) => account.platform === 'jd')
  const taobao = accounts.data?.find((account) => account.platform === 'taobao')
  const loggedCount = [jd, taobao].filter(
    (account) => account?.status === 'logged_in'
  ).length
  const productCount = products.data?.length ?? 0
  const hasProducts = productCount > 0
  const dataDir = health.data?.data_dir ?? appInfo.data?.dataDir ?? '—'

  return (
    <div>
      <PageHeader
        title="仪表盘"
        description="官方店铺价格监测。价格每 30 分钟刷新，刷新史低时通过 ServerChan 推送。"
      >
        <button
          type="button"
          onClick={() => {
            void products.refetch()
            void health.refetch()
          }}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          <RefreshCw className="h-4 w-4" />
          刷新
        </button>
        <Link
          to="/add"
          className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800"
        >
          <Plus className="h-4 w-4" />
          添加商品
        </Link>
      </PageHeader>

      {products.isError ? (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          读取商品失败：
          {products.error instanceof Error ? products.error.message : '未知错误'}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="监控商品"
          value={`${productCount} 个`}
          hint={hasProducts ? '点击卡片查看价格曲线' : '还没有添加商品'}
        />
        <StatCard
          label="平台账号"
          value={`${loggedCount} / 2 已登录`}
          hint={`京东：${jd ? statusLabel(jd.status) : '加载中'} · 淘宝：${
            taobao ? statusLabel(taobao.status) : '加载中'
          }`}
        />
        <StatCard
          label="轮询间隔"
          value={`${settings.data?.poll_interval_minutes ?? 30} 分钟`}
          hint="可在设置里调整"
        />
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-400">
            <StatusDot tone={health.isError ? 'error' : health.data ? 'ok' : 'idle'} />
            后端状态
          </div>
          <div className="mt-2 text-lg font-semibold text-slate-900">
            {health.isPending ? '连接中…' : health.isError ? '未连接' : '运行中'}
          </div>
          <div className="mt-1 break-all text-xs text-slate-500" title={dataDir}>
            {dataDir}
          </div>
        </section>
      </div>

      {!hasProducts && !products.isPending ? (
        <section className="mt-6 overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 p-6 text-white">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-white/10 p-2">
              <Smartphone className="h-5 w-5 text-emerald-300" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">添加第一个商品</h2>
              <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-300">
                先登录平台账号，再按型号搜索或粘贴京东/淘宝/天猫商品链接。系统只允许官方旗舰店与京东官方自营，并会按品牌再次校验；同一 SKU 会自动跨平台比价。
              </p>
            </div>
          </div>
          <div className="mt-6 grid gap-3 md:grid-cols-3">
            <Link
              to="/accounts"
              className="rounded-xl border border-white/10 bg-white/5 p-4 transition hover:bg-white/10"
            >
              <div className="text-xs font-medium text-emerald-300">第一步</div>
              <div className="mt-1 text-sm font-semibold">登录京东 / 淘宝</div>
              <div className="mt-1 text-xs text-slate-400">扫码登录，不保存密码</div>
            </Link>
            <Link
              to="/add"
              className="rounded-xl border border-white/10 bg-white/5 p-4 transition hover:bg-white/10"
            >
              <div className="text-xs font-medium text-emerald-300">第二步</div>
              <div className="mt-1 text-sm font-semibold">添加商品</div>
              <div className="mt-1 text-xs text-slate-400">按型号搜索或粘贴链接，指定 SKU</div>
            </Link>
            <div className="rounded-xl border border-white/10 bg-white/5 p-4">
              <div className="text-xs font-medium text-emerald-300">第三步</div>
              <div className="mt-1 text-sm font-semibold">等待抓价</div>
              <div className="mt-1 text-xs text-slate-400">每 30 分钟轮询，刷新史低推送</div>
            </div>
          </div>
          <div className="mt-5 flex items-center gap-2 text-sm text-emerald-300">
            <ArrowRight className="h-4 w-4" />
            当前还没有商品
          </div>
        </section>
      ) : null}

      {products.isPending ? (
        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((item) => (
            <div
              key={item}
              className="h-44 animate-pulse rounded-2xl border border-slate-200 bg-white"
            />
          ))}
        </div>
      ) : null}

      {hasProducts ? (
        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {products.data?.map((product) => (
            <ProductCard key={product.id} product={product} />
          ))}
        </div>
      ) : null}

      <div className="mt-6 flex items-start gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm leading-6 text-emerald-800">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
        <p>
          只监控天猫/京东官方旗舰店和京东官方自营；店铺类型或品牌不一致时不会启用。同一商品可绑定多个平台，史低与推送只认全平台最低价，价格来自页面展示与可见券估算，最终以下单结算为准。
        </p>
      </div>
    </div>
  )
}
