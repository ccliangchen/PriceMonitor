import type { JSX } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts'

import type { PricePoint } from '@/lib/types'

function formatDay(value: number): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit'
  }).format(new Date(value))
}

export function PriceChart({ points }: { points: PricePoint[] }): JSX.Element {
  if (points.length < 2) {
    return (
      <div className="flex h-64 items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-400">
        至少完成两次抓取后，这里会显示价格曲线
      </div>
    )
  }

  const data = points.map((point) => ({
    ts: new Date(point.captured_at).getTime(),
    price: point.lowest_price_cents / 100,
    platform: point.lowest_platform
  }))

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#0f172a" stopOpacity={0.18} />
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
            formatter={(value) => [
              `¥${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`,
              '全平台最低价'
            ]}
            contentStyle={{
              borderRadius: 12,
              border: '1px solid #e2e8f0',
              fontSize: 12
            }}
          />
          <Area
            type="monotone"
            dataKey="price"
            stroke="#0f172a"
            strokeWidth={2}
            fill="url(#priceGradient)"
            dot={false}
            activeDot={{ r: 4 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
