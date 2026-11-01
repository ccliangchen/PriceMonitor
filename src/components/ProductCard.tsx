import type { JSX } from 'react'
import { ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import {
  formatDateTime,
  formatPrice,
  priceSourceLabel,
  statusLabel
} from '@/lib/format'
import type { ProductSummary } from '@/lib/types'
import { PlatformBadge } from './PlatformBadge'

export function ProductCard({ product }: { product: ProductSummary }): JSX.Element {
  const pageLow = product.page_low_cents
  const isAtLow =
    product.current_price_cents !== null &&
    pageLow !== null &&
    product.current_price_cents <= pageLow

  return (
    <Link
      to={`/products/${product.id}`}
      className="group block rounded-2xl border border-slate-200 bg-white p-5 transition hover:border-slate-300 hover:shadow-sm"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-900">{product.name}</div>
          <div className="mt-1 text-xs text-slate-500">
            {product.ram_gb}GB+{product.storage_gb}GB
            {product.color ? ` · ${product.color}` : ''}
          </div>
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
          <div className="text-[11px] text-slate-400">页面史低</div>
          <div className="text-sm font-medium text-emerald-600">
            {pageLow !== null ? formatPrice(pageLow) : '—'}
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
          当前就是页面史低
        </div>
      ) : null}
    </Link>
  )
}
