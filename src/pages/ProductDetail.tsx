import type { JSX } from 'react'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  ExternalLink,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  ShieldAlert,
  Tag,
  Trash2
} from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { PageHeader } from '@/components/PageHeader'
import { PlatformBadge } from '@/components/PlatformBadge'
import { PriceChart } from '@/components/PriceChart'
import {
  calibrateListing,
  deleteProduct,
  fetchListingPrices,
  fetchPrices,
  fetchProduct,
  fetchSettings,
  refreshProduct,
  updateProductMonitoring,
  updateListing,
  verifyListing
} from '@/lib/api'
import {
  formatDateTime,
  formatPrice,
  platformLabel,
  priceSourceLabel,
  shopTypeLabel,
  statusLabel
} from '@/lib/format'
import type { PriceRange } from '@/lib/types'

const RANGES: Array<{ value: PriceRange; label: string }> = [
  { value: '7d', label: '7 天' },
  { value: '30d', label: '30 天' },
  { value: '90d', label: '90 天' },
  { value: 'all', label: '全部' }
]

interface CouponItem {
  raw?: string
  applied?: boolean
  amount_cents?: number
}

export default function ProductDetail(): JSX.Element {
  const params = useParams<{ productId: string }>()
  const productId = Number(params.productId)
  const validId = Number.isFinite(productId) && productId > 0
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [range, setRange] = useState<PriceRange>('30d')

  const product = useQuery({
    queryKey: ['product', productId],
    queryFn: () => fetchProduct(productId),
    enabled: validId,
    refetchInterval: 5000
  })
  const prices = useQuery({
    queryKey: ['prices', productId, range],
    queryFn: () => fetchPrices(productId, range),
    enabled: validId,
    refetchInterval: 10000
  })
  const listingPrices = useQuery({
    queryKey: ['listing-prices', productId, range],
    queryFn: () => fetchListingPrices(productId, range),
    enabled: validId,
    refetchInterval: 10000
  })
  const settings = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
    staleTime: 60000
  })
  const checkoutFreshHours = settings.data?.checkout_interval_hours ?? 6
  const refresh = useMutation({
    mutationFn: () => refreshProduct(productId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['product', productId] })
      void queryClient.invalidateQueries({ queryKey: ['prices', productId] })
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
    }
  })
  const verify = useMutation({
    mutationFn: (listingId: number) => verifyListing(listingId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['product', productId] })
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
    }
  })
  const calibrate = useMutation({
    mutationFn: (listingId: number) => calibrateListing(listingId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['product', productId] })
      void queryClient.invalidateQueries({ queryKey: ['prices', productId] })
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
    }
  })
  const toggle = useMutation({
    mutationFn: (payload: { id: number; status: 'active' | 'paused' }) =>
      updateListing(payload.id, payload.status),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['product', productId] })
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
    }
  })
  const monitoring = useMutation({
    mutationFn: (enabled: boolean) => updateProductMonitoring(productId, enabled),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['product', productId] })
      void queryClient.invalidateQueries({ queryKey: ['products'] })
    }
  })
  const remove = useMutation({
    mutationFn: () => deleteProduct(productId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
      navigate('/')
    }
  })

  if (!validId) {
    return (
      <div>
        <PageHeader title="商品详情" />
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          商品编号无效。<Link to="/" className="ml-1 underline">返回仪表盘</Link>
        </div>
      </div>
    )
  }

  if (product.isPending) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-slate-400">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        加载商品…
      </div>
    )
  }

  if (product.isError || !product.data) {
    return (
      <div>
        <PageHeader title="商品详情" />
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {product.error instanceof Error ? product.error.message : '商品不存在'}
          <Link to="/" className="ml-2 underline">返回仪表盘</Link>
        </div>
      </div>
    )
  }

  const data = product.data

  return (
    <div>
      <PageHeader
        title={data.name}
        description={`${data.listing_count} 个链接 · ${statusLabel(data.status)}`}
      >
        <Link
          to="/"
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          <ArrowLeft className="h-4 w-4" />
          返回
        </Link>
        <Link
          to={`/add?productId=${data.id}`}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          添加链接
        </Link>
        <button
          type="button"
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending || !data.monitoring_enabled || data.status !== 'active'}
          className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
        >
          {refresh.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          立即刷新
        </button>
        <button
          type="button"
          onClick={() => monitoring.mutate(!data.monitoring_enabled)}
          disabled={monitoring.isPending}
          className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium disabled:opacity-50 ${
            data.monitoring_enabled
              ? 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
              : 'bg-emerald-600 text-white hover:bg-emerald-700'
          }`}
        >
          {monitoring.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : data.monitoring_enabled ? (
            <Pause className="h-4 w-4" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          {data.monitoring_enabled ? '暂停监测' : '开启监测'}
        </button>
        <button
          type="button"
          onClick={() => {
            if (window.confirm(`确定删除“${data.name}”？该商品的监控链接和价格历史也会删除，无法撤销。`)) {
              remove.mutate()
            }
          }}
          disabled={remove.isPending}
          className="inline-flex items-center gap-2 rounded-lg border border-rose-200 bg-white px-3 py-2 text-sm font-medium text-rose-700 hover:bg-rose-50 disabled:opacity-50"
        >
          {remove.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Trash2 className="h-4 w-4" />
          )}
          删除商品
        </button>
      </PageHeader>

      {refresh.isSuccess ? (
        <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
          已排入抓取队列，价格更新需要几秒。
        </div>
      ) : null}
      {!data.monitoring_enabled ? (
        <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          此商品已暂停监测，自动轮询和立即刷新均已停止；开启后会在原轮询间隔内继续。单独暂停的链接仍需在下方恢复。
        </div>
      ) : null}
      {data.monitoring_enabled && data.status !== 'active' ? (
        <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          商品监测已开启，但当前没有可轮询的链接。请在下方恢复需要监测的京东或淘宝链接。
        </div>
      ) : null}
      {monitoring.isError ? (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {monitoring.error instanceof Error ? monitoring.error.message : '切换监测状态失败'}
        </div>
      ) : null}
      {refresh.isError ? (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {refresh.error instanceof Error ? refresh.error.message : '刷新失败'}
        </div>
      ) : null}
      {remove.isError ? (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {remove.error instanceof Error ? remove.error.message : '删除失败'}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="text-xs font-medium uppercase tracking-wider text-slate-400">
            当前最低价
          </div>
          <div className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">
            {data.current_price_cents !== null
              ? formatPrice(data.current_price_cents)
              : '等待首次抓取'}
          </div>
          <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">
            <PlatformBadge platform={data.current_platform} />
            <span>{data.current_shop_name}</span>
            <span>{priceSourceLabel(data.current_source)}</span>
          </div>
        </section>
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="text-xs font-medium uppercase tracking-wider text-slate-400">
            商品史低
          </div>
          <div className="mt-2 text-xl font-semibold text-emerald-600">
            {data.history_low_cents !== null
              ? formatPrice(data.history_low_cents)
              : '—'}
          </div>
          <div className="mt-2 flex items-center gap-1 text-xs text-slate-500">
            <PlatformBadge platform={data.history_low_platform} />
            <span>{data.history_low_shop_name ?? '所有链接最低'}</span>
          </div>
        </section>
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="text-xs font-medium uppercase tracking-wider text-slate-400">
            实付史低
          </div>
          <div className="mt-2 text-xl font-semibold text-slate-700">
            {data.checkout_low_cents !== null
              ? formatPrice(data.checkout_low_cents)
              : '无实付记录'}
          </div>
          <div className="mt-2 text-xs text-slate-500">
            {data.checkout_last_at
              ? `最近校准 ${formatDateTime(data.checkout_last_at)}`
              : '不影响自动页面价监控'}
          </div>
        </section>
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="text-xs font-medium uppercase tracking-wider text-slate-400">
            监测链接
          </div>
          <div className="mt-2 text-lg font-semibold text-slate-900">
            {data.listing_count} 个链接
          </div>
          <div className="mt-2 text-xs text-slate-500">
            {data.listings
              .map((item) => `${platformLabel(item.platform)}/${item.shop_name}`)
              .join('、') || '—'}
          </div>
        </section>
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="text-xs font-medium uppercase tracking-wider text-slate-400">
            上次抓取
          </div>
          <div className="mt-2 text-lg font-semibold text-slate-900">
            {formatDateTime(data.last_checked_at)}
          </div>
          <div className="mt-2 text-xs text-slate-500">
            {priceSourceLabel(data.current_source)}
          </div>
        </section>
      </div>

      {data.listing_count === 0 ? (
        <div className="mt-6 rounded-xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-600">
          这个商品还没有链接。<Link to={`/add?productId=${data.id}`} className="ml-1 font-medium text-slate-900 underline">添加京东、淘宝或天猫商品链接</Link>
        </div>
      ) : null}

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">价格曲线</h2>
            <p className="mt-1 text-xs text-slate-500">
              每条链接各有一条价格线，深色汇总线取当时所有链接的最低价。
            </p>
          </div>
          <div className="flex rounded-lg bg-slate-100 p-1">
            {RANGES.map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => setRange(item.value)}
                className={`rounded-md px-2.5 py-1 text-xs transition ${
                  range === item.value
                    ? 'bg-white font-medium text-slate-900 shadow-sm'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
        <div className="mt-4">
          {prices.isPending ? (
            <div className="flex h-64 items-center justify-center text-sm text-slate-400">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              加载曲线…
            </div>
          ) : (
            <PriceChart
              points={prices.data ?? []}
              series={listingPrices.data ?? []}
            />
          )}
        </div>
      </section>

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Tag className="h-4 w-4" />
          链接明细
        </div>
        <div className="mt-4 space-y-4">
          {data.listings.map((item) => {
            const itemCoupons = (item.coupon_breakdown ?? []) as CouponItem[]
            const checkoutAt = item.checkout_captured_at
              ? new Date(item.checkout_captured_at).getTime()
              : null
            const pageAt = item.price_captured_at
              ? new Date(item.price_captured_at).getTime()
              : null
            const checkoutStale =
              checkoutAt === null ||
              Date.now() - checkoutAt > checkoutFreshHours * 3600 * 1000
            const pageChangedFirst =
              checkoutAt !== null && pageAt !== null && pageAt > checkoutAt
            const captchaPaused = item.platform !== 'taobao' && item.last_attempt_status === 'captcha'
            return (
              <div
                key={item.id}
                className="rounded-xl border border-slate-100 bg-slate-50/60 p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <PlatformBadge platform={item.platform} />
                      <span className="text-sm font-medium text-slate-900">
                        {item.shop_name}
                      </span>
                      <span className="rounded-full bg-white px-2 py-0.5 text-[11px] text-slate-500">
                        {shopTypeLabel(item.shop_type)}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      状态：{statusLabel(item.status)} · 采价：{item.platform === 'jd' ? '浏览器扩展' : '应用内浏览器优先，失败时使用扩展'} · 上次抓取：{formatDateTime(item.last_checked_at)}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">{item.title}</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() =>
                        toggle.mutate({
                          id: item.id,
                          status: item.status === 'active' ? 'paused' : 'active'
                        })
                      }
                      disabled={
                        toggle.isPending ||
                        item.status === 'verifying' ||
                        captchaPaused
                      }
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                    >
                      {item.status === 'active' ? (
                        <Pause className="h-3.5 w-3.5" />
                      ) : (
                        <Play className="h-3.5 w-3.5" />
                      )}
                      {item.status === 'active'
                        ? '暂停监控'
                        : captchaPaused
                          ? '需先验证'
                          : '恢复监控'}
                    </button>
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-xs font-medium text-slate-600 hover:text-slate-900"
                    >
                      打开商品
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  </div>
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  <div className="rounded-lg bg-white p-3">
                    <div className="text-[11px] text-slate-400">当前采纳价</div>
                    <div className="mt-1 text-sm font-semibold text-slate-900">
                      {item.effective_price_cents !== null ? formatPrice(item.effective_price_cents) : '等待首次采价'}
                    </div>
                  </div>
                  <div className="rounded-lg bg-white p-3">
                    <div className="text-[11px] text-slate-400">页面预估价</div>
                    <div className="mt-1 text-sm font-medium text-emerald-600">
                      {item.estimated_price_cents !== null
                        ? formatPrice(item.estimated_price_cents)
                        : '暂无页面预估价'}
                    </div>
                  </div>
                  <div className="rounded-lg bg-white p-3">
                    <div className="text-[11px] text-slate-400">实付结算价</div>
                    <div className="mt-1 text-sm font-medium text-slate-800">
                      {item.checkout_price_cents !== null
                        ? formatPrice(item.checkout_price_cents)
                        : item.platform === 'jd'
                          ? '未记录'
                          : '未校准'}
                    </div>
                    <div className="mt-0.5 text-[10px] text-slate-400">
                      {item.checkout_captured_at
                        ? formatDateTime(item.checkout_captured_at)
                        : item.platform === 'jd'
                          ? '京东价格自动读取 PC 商品页'
                          : '手动校准后更新'}
                    </div>
                  </div>
                </div>

                {item.platform !== 'jd' ? (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => calibrate.mutate(item.id)}
                      disabled={
                        calibrate.isPending ||
                        item.status !== 'active' ||
                        item.last_checkout_status === 'running'
                      }
                      className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                    >
                      {calibrate.isPending ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Tag className="h-3.5 w-3.5" />
                      )}
                      手动校准实付
                    </button>
                    <span className="text-[11px] text-slate-400">
                      会打开可见浏览器走到确认订单页读取实付款，不会提交订单；如未自动跳转，请手动点击“立即购买”。
                    </span>
                  </div>
                ) : null}
                {item.platform !== 'jd' && (checkoutStale || pageChangedFirst) ? (
                  <div className="mt-2 text-[11px] text-amber-700">
                    {checkoutStale
                      ? `实付结算价未校准或已超过 ${checkoutFreshHours} 小时（手动校准）；页面预估价正常抓取。`
                      : '页面预估价在上次手动校准后发生变化，建议重新校准实付。'}
                  </div>
                ) : null}
                {calibrate.isSuccess ? (
                  <div className="mt-2 text-xs text-emerald-700">
                    {calibrate.data?.message}
                  </div>
                ) : null}
                {calibrate.isError ? (
                  <div className="mt-2 text-xs text-rose-700">
                    {calibrate.error instanceof Error
                      ? calibrate.error.message
                      : '校准失败'}
                  </div>
                ) : null}
                {item.last_checkout_status === 'running' ? (
                  <div className="mt-2 text-xs text-amber-700">
                    结算校准进行中，请在弹出的浏览器窗口中操作；最多等待 3 分钟。
                  </div>
                ) : null}
                {item.last_checkout_status === 'failed' ? (
                  <div className="mt-2 text-xs text-rose-700">
                    上次校准失败：{item.last_checkout_error ?? '未知错误'}
                    {item.last_checkout_at
                      ? `（${formatDateTime(item.last_checkout_at)}）`
                      : ''}
                  </div>
                ) : null}

                {item.last_attempt_status && item.last_attempt_status !== 'ok' ? (
                  <div className={`mt-3 rounded-lg border p-3 text-xs leading-5 ${item.last_attempt_status === 'low_confidence' ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-rose-200 bg-rose-50 text-rose-700'}`}>
                    {item.last_attempt_status === 'low_confidence' ? '最近一次价格未采纳：' : '最近一次抓取失败：'}
                    {item.last_attempt_error ?? statusLabel(item.last_attempt_status)}
                    （{formatDateTime(item.last_attempt_at)}）。上方显示的是上一次成功抓取的价格。
                  </div>
                ) : null}

                {item.status === 'verifying' || captchaPaused ? (
                  <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-800">
                    <div>
                      {platformLabel(item.platform)}要求人工验证。点击下方按钮，在弹出的 Edge
                      窗口完成滑块/验证，完成后会自动恢复监控。
                    </div>
                    <button
                      type="button"
                      onClick={() => verify.mutate(item.id)}
                      disabled={verify.isPending || item.status === 'verifying'}
                      className="mt-2 inline-flex items-center gap-2 rounded-lg bg-amber-600 px-3 py-2 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50"
                    >
                      {verify.isPending || item.status === 'verifying' ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <ShieldAlert className="h-3.5 w-3.5" />
                      )}
                      {item.status === 'verifying'
                        ? '验证中…'
                        : `打开${platformLabel(item.platform)}验证页`}
                    </button>
                    {verify.isSuccess ? (
                      <div className="mt-2 text-emerald-700">
                        验证窗口已打开，请在弹窗中完成验证。
                      </div>
                    ) : null}
                    {verify.isError ? (
                      <div className="mt-2 text-rose-700">
                        {verify.error instanceof Error
                          ? verify.error.message
                          : '打开验证页失败'}
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {itemCoupons.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {itemCoupons.map((coupon, index) => (
                      <span
                        key={`${coupon.raw ?? 'coupon'}-${index}`}
                        className={`rounded-full px-2.5 py-1 text-[11px] ${
                          coupon.applied
                            ? 'bg-emerald-50 text-emerald-700'
                            : 'bg-slate-100 text-slate-400 line-through'
                        }`}
                      >
                        {coupon.raw ?? '优惠券'}
                      </span>
                    ))}
                  </div>
                ) : (
                  <div className="mt-3 text-xs text-slate-400">未识别到可见优惠券</div>
                )}
                <div className="mt-2 text-[10px] text-slate-400">
                  券明细仅供参考，最终以页面预估价为准。
                </div>
              </div>
            )
          })}
        </div>
        {data.recent_prices.length === 0 ? (
          <p className="mt-4 text-xs text-slate-400">
            第一次抓取只建立史低基线，之后每 30 分钟记录一次。
          </p>
        ) : null}
      </section>
    </div>
  )
}
