import { describe, expect, it } from 'vitest'
import { isTaiwanMarketOpen } from './marketHours'

describe('isTaiwanMarketOpen', () => {
  it('returns true during regular Taiwan weekday market hours', () => {
    expect(isTaiwanMarketOpen(new Date('2026-08-17T02:00:00.000Z'))).toBe(true)
  })

  it('returns false before market open', () => {
    expect(isTaiwanMarketOpen(new Date('2026-08-17T00:59:00.000Z'))).toBe(false)
  })

  it('keeps streaming through 13:30 Taiwan time', () => {
    expect(isTaiwanMarketOpen(new Date('2026-08-17T05:30:00.000Z'))).toBe(true)
  })

  it('returns false from 13:31 Taiwan time', () => {
    expect(isTaiwanMarketOpen(new Date('2026-08-17T05:31:00.000Z'))).toBe(false)
  })

  it('returns false on weekends', () => {
    expect(isTaiwanMarketOpen(new Date('2026-08-16T02:00:00.000Z'))).toBe(false)
  })
})
