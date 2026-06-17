import { describe, it, expect } from 'vitest'
import { parseServerTimeMs, projectElapsedSeconds } from './OptimizationProgressCard'

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

describe('projectElapsedSeconds', () => {
  it('returns the server base when no client time has passed (skew cannot leak)', () => {
    // The instant the base is received, anchoredAt == now, so the readout is
    // exactly the server-reported elapsed — regardless of any client/server
    // clock skew. This is the ~3m30s-jump regression: the timer must not add
    // the skew the moment polling swaps in the server value.
    expect(projectElapsedSeconds(12, 1_000_000, 1_000_000)).toBe(12)
  })

  it('adds only the client-clock delta since the base was anchored', () => {
    const anchoredAt = 5_000_000
    expect(projectElapsedSeconds(12, anchoredAt, anchoredAt + 7_000)).toBe(19)
  })

  it('depends only on the now−anchor delta, not absolute clock values', () => {
    // Shifting both anchor and now by the same (arbitrary, skew-like) offset
    // leaves the result unchanged.
    const a = projectElapsedSeconds(30, 1_000_000, 1_004_000)
    const b = projectElapsedSeconds(30, 1_000_000 + 210_000, 1_004_000 + 210_000)
    expect(a).toBe(b)
    expect(a).toBe(34)
  })

  it('never goes negative', () => {
    expect(projectElapsedSeconds(0, 2_000_000, 1_000_000)).toBe(0)
  })
})
