import { describe, it, expect } from 'vitest'
import { parseServerTimeMs } from './OptimizationProgressCard'

describe('parseServerTimeMs', () => {
  // Same wall-clock instant: 2026-06-15T18:00:00 UTC == 1781632800000 ms.
  const UTC_MS = Date.UTC(2026, 5, 15, 18, 0, 0)

  it('parses a timezone-less ISO string as UTC (the Mongo naive-datetime case)', () => {
    // No offset — the browser would otherwise read this as local time.
    expect(parseServerTimeMs('2026-06-15T18:00:00')).toBe(UTC_MS)
    expect(parseServerTimeMs('2026-06-15T18:00:00.000000')).toBe(UTC_MS)
  })

  it('respects an explicit +00:00 offset', () => {
    expect(parseServerTimeMs('2026-06-15T18:00:00+00:00')).toBe(UTC_MS)
  })

  it('respects a trailing Z', () => {
    expect(parseServerTimeMs('2026-06-15T18:00:00Z')).toBe(UTC_MS)
  })

  it('respects a non-UTC offset rather than forcing UTC', () => {
    // 18:00 at +02:00 is 16:00 UTC — must not be clobbered to 18:00 UTC.
    expect(parseServerTimeMs('2026-06-15T18:00:00+02:00')).toBe(Date.UTC(2026, 5, 15, 16, 0, 0))
  })

  it('a naive timestamp yields a non-negative elapsed (no future-start clamp to 0)', () => {
    // Regression: a recent naive start must read as the past, so now - start >= 0.
    const recentNaive = new Date(Date.now() - 5000).toISOString().replace('Z', '')
    expect(Date.now() - parseServerTimeMs(recentNaive)).toBeGreaterThanOrEqual(0)
  })
})
