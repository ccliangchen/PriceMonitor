import { describe, expect, it } from 'vitest'
import { buildChartRows } from './PriceChart'
import type { ListingPriceSeries } from '../lib/types'

describe('combined product price curve', () => {
  it('keeps two links from the same shop separate and takes their running minimum', () => {
    const series: ListingPriceSeries[] = [
      {
        listing_id: 1, platform: 'jd', shop_name: '普通灯具店',
        points: [
          { captured_at: '2026-11-10T00:00:00Z', effective_price_cents: 10000, source: 'page' },
          { captured_at: '2026-11-10T02:00:00Z', effective_price_cents: 7000, source: 'page' }
        ]
      },
      {
        listing_id: 2, platform: 'jd', shop_name: '普通灯具店',
        points: [
          { captured_at: '2026-11-10T01:00:00Z', effective_price_cents: 8000, source: 'page' }
        ]
      }
    ]
    const rows = buildChartRows([], series)
    expect(rows.map((row) => row.global)).toEqual([100, 80, 70])
    expect(rows.map((row) => row.shop_0)).toEqual([100, 100, 70])
    expect(rows.map((row) => row.shop_1)).toEqual([undefined, 80, 80])
  })
})
