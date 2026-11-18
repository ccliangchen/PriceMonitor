import type { JSX } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts'

import { platformLabel } from '../lib/format'
import type { ListingPriceSeries, PricePoint } from '../lib/types'

interface ChartRow {
  ts: number
  global?: number
  [key: string]: number | undefined
}

const FALLBACK_COLORS = ['#0ea5e9', '#8b5cf6', '#10b981', '#64748b', '#ec4899']

function formatDay(value: number): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit'
  }).format(new Date(value))
}

function colorFor(platform: string, index: number): string {
  if (platform === 'jd') {
    return index % 2 === 0 ? '#e11d48' : '#fb7185'
  }
  if (platform === 'taobao') {
    return index % 2 === 0 ? '#f97316' : '#fb923c'
  }
  return FALLBACK_COLORS[index % FALLBACK_COLORS.length]
}

function seriesKey(index: number): string {
  return `shop_${index}`
}

function lastValue<T>(
  items: T[],
  ts: number,
  getTs: (item: T) => number,
  getValue: (item: T) => number
): number | undefined {
  let result: number | undefined
  for (const item of items) {
    if (getTs(item) > ts) {
      break
    }
    result = getValue(item)
  }
  return result
}

export function buildChartRows(points: PricePoint[], series: ListingPriceSeries[]): ChartRow[] {
  const timestamps = [
    ...new Set([
      ...points.map((point) => new Date(point.captured_at).getTime()),
      ...series.flatMap((item) =>
        item.points.map((point) => new Date(point.captured_at).getTime())
      )
    ])
  ]
    .filter((value) => Number.isFinite(value))
    .sort((left, right) => left - right)

  return timestamps.map((ts) => {
    const row: ChartRow = { ts }
    const values: number[] = []
    for (const [groupIndex, item] of series.entries()) {
      const value = lastValue(
        item.points, ts,
        (point) => new Date(point.captured_at).getTime(),
        (point) => point.effective_price_cents / 100
      )
      if (value !== undefined) {
        row[seriesKey(groupIndex)] = value
        values.push(value)
      }
    }
    row.global = values.length > 0 ? Math.min(...values) : lastValue(
      points, ts,
      (point) => new Date(point.captured_at).getTime(),
      (point) => point.lowest_price_cents / 100
    )
    return row
  })
}

export function PriceChart({
  points,
  series = []
}: {
  points: PricePoint[]
  series?: ListingPriceSeries[]
}): JSX.Element {
  const data = buildChartRows(points, series)
  if (data.length < 2) {
    return (
      <div className="flex h-64 items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-400">
        至少完成两次抓取后，这里会显示价格曲线
      </div>
    )
  }
  const colors = new Map<number, string>()
  const platformCounts: Record<string, number> = {}
  series.forEach((item, groupIndex) => {
    const platform = item.platform
    const index = platformCounts[platform] ?? 0
    colors.set(groupIndex, colorFor(platform, index))
    platformCounts[platform] = index + 1
  })

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#0f172a" stopOpacity={0.16} />
              <stop offset="95%" stopColor="#0f172a" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
          <XAxis
            dataKey="ts"
            type="number"
            scale="time"
            domain={['dataMin', 'dataMax']}
            tickLine={false}
            axisLine={false}
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            tickFormatter={(value: number) => formatDay(value)}
          />
          <YAxis
            width={72}
            tickLine={false}
            axisLine={false}
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            domain={['auto', 'auto']}
            tickFormatter={(value: number) => `¥${Number(value).toLocaleString('zh-CN')}`}
          />
          <Tooltip
            labelFormatter={(value) => new Date(Number(value)).toLocaleString('zh-CN')}
            formatter={(value, name) => [
              `¥${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`,
              String(name)
            ]}
            contentStyle={{
              borderRadius: 12,
              border: '1px solid #e2e8f0',
              fontSize: 12
            }}
          />
          <Legend
            verticalAlign="bottom"
            height={28}
            wrapperStyle={{ fontSize: 11, color: '#64748b' }}
          />
          <Area
            type="stepAfter"
            dataKey="global"
            name="所有链接最低价"
            stroke="#0f172a"
            strokeWidth={2}
            fill="url(#priceGradient)"
            dot={false}
            activeDot={{ r: 4 }}
            connectNulls
          />
          {series.map((item, groupIndex) => (
            <Line
              key={item.listing_id}
              type="stepAfter"
              dataKey={seriesKey(groupIndex)}
              name={`${platformLabel(item.platform)} · ${item.shop_name} · 链接 #${item.listing_id}`}
              stroke={colors.get(groupIndex)}
              strokeWidth={1.7}
              dot={false}
              activeDot={{ r: 3 }}
              connectNulls
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
