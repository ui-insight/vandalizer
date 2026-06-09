import { useCallback, useEffect, useMemo, useRef } from 'react'

interface StartOptions<T> {
  fetch: () => Promise<T>
  intervalMs: number
  /** When this returns true for a polled result, polling auto-stops. */
  isTerminal: (data: T) => boolean
  onUpdate: (data: T) => void
  onError?: (e: unknown) => void
}

/**
 * Generic interval-based poller. Caller drives lifecycle via the returned
 * `start` / `stop`; the hook also clears the interval on unmount.
 *
 * Designed for autovalidate run polling (KB / extraction / workflow share the
 * same "fetch run state every Ns until terminal" shape) but generic enough
 * for any periodic fetch.
 */
export function useIntervalPoll<T>() {
  const ref = useRef<number | null>(null)

  const stop = useCallback(() => {
    if (ref.current != null) {
      window.clearInterval(ref.current)
      ref.current = null
    }
  }, [])

  const start = useCallback((opts: StartOptions<T>) => {
    stop()
    ref.current = window.setInterval(async () => {
      try {
        const fresh = await opts.fetch()
        opts.onUpdate(fresh)
        if (opts.isTerminal(fresh)) stop()
      } catch (e) {
        if (opts.onError) opts.onError(e)
        else console.error('Polling failed', e)
      }
    }, opts.intervalMs)
  }, [stop])

  useEffect(() => () => stop(), [stop])

  // Stable object so callers can list the hook's return value in effect/callback
  // deps without triggering a render loop. Without useMemo, `{ start, stop }` is
  // a fresh object every render, which silently invalidates any useCallback that
  // depends on it.
  return useMemo(() => ({ start, stop }), [start, stop])
}
