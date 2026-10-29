import { afterEach, describe, expect, it, vi } from 'vitest'
import { formatFileDate, formatLocalTimestamp, parseServerTimestamp, relativeTime } from './time'

afterEach(() => vi.useRealTimers())

describe('server timestamps', () => {
  it.each(['2026-10-29T22:28:00', '2026-10-29 22:28:00', '2026-10-29T22:28:00Z',
    '2026-10-29T22:28:00+00:00', '2026-10-29T15:28:00-07:00'])('preserves the instant in %s', value => {
    expect(parseServerTimestamp(value).toISOString()).toBe('2026-10-29T22:28:00.000Z')
    expect(formatLocalTimestamp(value)).toBe(new Date('2026-10-29T22:28:00Z').toLocaleString(undefined, { timeZoneName: 'short' }))
  })

  it.each([
    ['2026-10-29T22:28:00', '3:28 PM'], // Pacific daylight time
    ['2026-12-29T22:28:00', '2:28 PM'], // Pacific standard time
    ['2026-03-08T09:30:00', '1:30 AM'], // Before the spring transition
    ['2026-03-08T10:30:00', '3:30 AM'], // After the spring transition
  ])('uses the Pacific offset for the event date: %s', (value, expected) => {
    expect(parseServerTimestamp(value).toLocaleTimeString('en-US', {
      timeZone: 'America/Los_Angeles', hour: 'numeric', minute: '2-digit',
    })).toBe(expected)
  })

  it('converts midnight UTC to the previous local calendar day', () => {
    expect(parseServerTimestamp('2026-10-30T00:28:00').toLocaleDateString('en-US', { timeZone: 'America/Los_Angeles' })).toBe('10/29/2026')
  })

  it('does not double-convert offset timestamps or reinterpret date-only values', () => {
    expect(parseServerTimestamp('2026-10-30T03:58:00+05:30').toISOString()).toBe('2026-10-29T22:28:00.000Z')
    expect(parseServerTimestamp('2026-10-29').getTime()).toBe(new Date('2026-10-29').getTime())
    expect(parseServerTimestamp('2026-10-29T22:28:00.123456').toISOString()).toBe('2026-10-29T22:28:00.123Z')
  })

  it('computes relative ages for older UTC responses instead of treating them as future events', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-29T22:38:00Z'))
    expect(relativeTime('2026-10-29T22:28:00')).toBe('10m ago')
    expect(formatFileDate('2026-10-29T22:28:00')).toBe('10m ago')
  })

  it.each([null, undefined, '', 'not a date'])('handles unavailable timestamps: %s', value => {
    expect(formatLocalTimestamp(value)).toBe('Time unavailable')
  })
})
