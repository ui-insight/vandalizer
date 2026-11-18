import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { consumePendingNext, PENDING_NEXT_KEY, rememberPendingNext, safeNextPath } from './pendingNext'

beforeEach(() => sessionStorage.clear())
afterEach(() => vi.useRealTimers())

describe('safeNextPath', () => {
  it('keeps a same-origin path with its query', () => {
    expect(safeNextPath('/?kb=abc')).toBe('/?kb=abc')
  })
  it('keeps a path with an encoded space or tab in its query', () => {
    expect(safeNextPath('/?q=a%20b%09c#top')).toBe('/?q=a%20b%09c#top')
  })
  it.each(['//evil.example/x', 'https://evil.example', '/\\evil.example', 'kb=abc', '', undefined, null])(
    'rejects %s', (raw) => { expect(safeNextPath(raw)).toBeNull() },
  )
  // A browser drops tabs and newlines from a URL before following it, so
  // each of these is "//evil.example" or "/\evil.example" when it is used.
  it.each([
    '/\t/evil.example/x', '/\n/evil.example', '/\r/evil.example', '/\t\\evil.example',
    '/\r\n/evil.example', '/ /evil.example', '/\u0000/evil.example',
  ])('rejects a path hiding a host behind a control character (%j)', (raw) => {
    expect(safeNextPath(raw)).toBeNull()
  })
  it('does not park such a path for after sign-in', () => {
    rememberPendingNext('/\t/evil.example/x')
    expect(sessionStorage.getItem(PENDING_NEXT_KEY)).toBeNull()
  })
})

describe('the link parked across single sign-on', () => {
  it('comes back once, then is gone', () => {
    rememberPendingNext('/?kb=abc')
    expect(consumePendingNext()).toBe('/?kb=abc')
    expect(consumePendingNext()).toBeNull()
  })

  it('is not parked when it is not a safe path', () => {
    rememberPendingNext('//evil.example')
    expect(sessionStorage.getItem(PENDING_NEXT_KEY)).toBeNull()
  })

  it('expires, so an abandoned sign-in does not redirect a later visit', () => {
    vi.useFakeTimers()
    rememberPendingNext('/?kb=abc')
    vi.advanceTimersByTime(11 * 60 * 1000)
    expect(consumePendingNext()).toBeNull()
    expect(sessionStorage.getItem(PENDING_NEXT_KEY)).toBeNull()
  })

  it.each(['not json', '{"path":"//evil.example","at":1e15}', '{"path":"/x"}'])('ignores a tampered value %s', (raw) => {
    sessionStorage.setItem(PENDING_NEXT_KEY, raw)
    expect(consumePendingNext()).toBeNull()
  })
})
