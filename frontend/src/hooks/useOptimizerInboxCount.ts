import { useEffect, useState } from 'react'
import { getOptimizerInboxCount, type OptimizerInboxCounts } from '../api/optimizerInbox'

/**
 * Badge counts for the tuning-suggestions inbox.
 *
 * Polled slowly on purpose: auto-tuning is rate-limited by a multi-hour
 * per-item cooldown, so a candidate appearing between polls is minutes-stale
 * at worst — and the endpoint access-checks every row it counts.
 *
 * State lives at module scope with one shared timer, because both the account
 * menu and the activity rail badge want the same number and neither should
 * cost a second poll.
 */
const POLL_MS = 5 * 60 * 1000

let cached: OptimizerInboxCounts | null = null
let timer: ReturnType<typeof setInterval> | null = null
let inFlight: Promise<void> | null = null
const subscribers = new Set<(counts: OptimizerInboxCounts | null) => void>()

function refresh(): Promise<void> {
  if (inFlight) return inFlight
  inFlight = getOptimizerInboxCount()
    .then(data => {
      cached = data
      subscribers.forEach(fn => fn(data))
    })
    .catch(() => {
      // Silent: a nav badge must never surface an error state.
    })
    .finally(() => { inFlight = null })
  return inFlight
}

export function useOptimizerInboxCount() {
  const [counts, setCounts] = useState<OptimizerInboxCounts | null>(cached)

  useEffect(() => {
    subscribers.add(setCounts)
    void refresh()
    if (!timer) timer = setInterval(() => void refresh(), POLL_MS)
    return () => {
      subscribers.delete(setCounts)
      if (subscribers.size === 0 && timer) {
        clearInterval(timer)
        timer = null
      }
    }
  }, [])

  // Rows the user can actually act on — candidates plus failures.
  const actionable = (counts?.needs_review ?? 0) + (counts?.failed ?? 0)
  return { counts, actionable, refresh }
}
