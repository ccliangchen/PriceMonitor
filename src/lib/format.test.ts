import { describe, expect, it } from 'vitest'

import { formatPrice, formatUptime } from './format'

describe('formatUptime', () => {
  it('formats seconds', () => {
    expect(formatUptime(42)).toBe('42 秒')
  })

  it('formats minutes', () => {
    expect(formatUptime(125)).toBe('2 分钟')
  })

  it('formats hours and minutes', () => {
    expect(formatUptime(3725)).toBe('1 小时 2 分钟')
  })
})

describe('formatPrice', () => {
  it('formats whole yuan with thousands separators', () => {
    expect(formatPrice(749900)).toBe('¥7,499')
  })

  it('keeps up to two decimals', () => {
    expect(formatPrice(749950)).toBe('¥7,499.5')
  })
})
