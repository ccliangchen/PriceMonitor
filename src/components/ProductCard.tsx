import type { JSX } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, Loader2, Pause, Play } from 'lucide-react'
import { Link } from 'react-router-dom'

import { updateProductMonitoring } from '@/lib/api'
import {
  formatDateTime,
  formatPrice,
  priceSourceLabel,
  statusLabel
} from '@/lib/format'
import type { ProductSummary } from '@/lib/types'
import { PlatformBadge } from './PlatformBadge'

export function ProductCard({ product }: { product: ProductSummary }): JSX.Element {
  const queryClient = useQueryClient()
  const monitoring = useMutation({
    mutationFn: () => updateProductMonitoring(product.id, !product.monitoring_enabled),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      void queryClient.invalidateQueries({ queryKey: ['product', product.id] })
    }
  })
  const pageLow = product.history_low_cents
  const isAtLow =
    product.current_price_cents !== null &&
    pageLow !== null &&
    product.current_price_cents <= pageLow

  return (
    <div className="group rounded-2xl border border-slate-200 bg-white p-5 transition hover:border-slate-300 hover:shadow-sm">
      <Link to={`/products/${product.id}`} className="block">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-900">{product.name}</div>
          <div className="mt-1 text-xs text-slate-500">{product.listing_count} 个链接</div>
        </div>
        <ArrowUpRight className="h-4 w-4 shrink-0 text-slate-300 transition group-hover:text-slate-500" />
      </div>

      <div className="mt-5 flex items-end justify-between gap-3">
        <div>
          <div className="text-2xl font-semibold tracking-tight text-slate-900">
            {product.current_price_cents !== null
              ? formatPrice(product.current_price_cents)
              : '暂无报价'}
          </div>
          <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
            <PlatformBadge platform={product.current_platform} />
            <span>
              {priceSourceLabel(product.current_source)}
            </span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-[11px] text-slate-400">商品史低</div>
          <div className="text-sm font-medium text-emerald-600">
            {pageLow !== null ? formatPrice(pageLow) : '—'}
          </div>
          <div className="text-[11px] text-slate-500">
            {product.history_low_platform === 'jd' ? '京东' : product.history_low_platform === 'taobao' ? '淘宝/天猫' : ''}
            {product.history_low_shop_name ? ` · ${product.history_low_shop_name}` : ''}
          </div>
          <div className="mt-1 text-[11px] text-slate-400">实付史低</div>
          <div className="text-xs text-slate-600">
            {product.checkout_low_cents !== null
              ? formatPrice(product.checkout_low_cents)
              : '未校准'}
          </div>
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3 text-[11px] text-slate-400">
        <span>{statusLabel(product.status)}</span>
        <span>
          {product.last_checked_at
            ? `上次 ${formatDateTime(product.last_checked_at)}`
            : '尚未抓取'}
        </span>
      </div>
      {isAtLow ? (
        <div className="mt-2 text-[11px] font-medium text-emerald-600">
          当前就是商品史低
        </div>
      ) : null}
      </Link>
      <div className="mt-4 border-t border-slate-100 pt-3">
        <button
          type="button"
          onClick={() => monitoring.mutate()}
          disabled={monitoring.isPending}
          className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium disabled:opacity-50 ${
            product.monitoring_enabled
              ? 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
              : 'bg-emerald-600 text-white hover:bg-emerald-700'
          }`}
        >
          {monitoring.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : product.monitoring_enabled ? (
            <Pause className="h-3.5 w-3.5" />
          ) : (
            <Play className="h-3.5 w-3.5" />
          )}
          {product.monitoring_enabled ? '暂停监测' : '开启监测'}
        </button>
        {monitoring.isError ? (
          <p className="mt-2 text-xs text-rose-600">
            {monitoring.error instanceof Error ? monitoring.error.message : '操作失败'}
          </p>
        ) : null}
        {product.monitoring_enabled && product.listing_count > 0 && product.status !== 'active' ? (
          <p className="mt-2 text-xs text-amber-700">商品开关已开启；请在详情页恢复单独暂停的链接。</p>
        ) : null}
      </div>
    </div>
  )
}
