import { useEffect, useState } from 'react'
import { getMyReviewCount } from '../api/reviews'

/**
 * Badge count for reviews assigned to the current user and still pending.
 *
 * Approvals block a workflow run, so this polls on the same 30s cadence as the
 * notification bell rather than the optimizer inbox's multi-minute one — a
 * reviewer who acts on a notification should see the badge clear, not sit on a
 * stale number.
 *
 * State lives at module scope with one shared timer because both the account
 * menu and the activity rail want the same number, and neither should cost a
 * second poll.
 */
const POLL_MS = 30 * 1000

let cached: number | null = null
let timer: ReturnType<typeof setInterval> | null = null
let inFlight: Promise<void> | null = null
const subscribers = new Set<(count: number) => void>()

function fetchOnce(): Promise<void> {
  inFlight = getMyReviewCount()
    .then(data => {
      cached = data.count
      subscribers.forEach(fn => fn(data.count))
    })
    .catch(() => {
      // Silent: a nav badge must never surface an error state.
    })
    .finally(() => { inFlight = null })
  return inFlight
}

/** Coalesce concurrent polls: the background timer must not stack requests. */
function refresh(): Promise<void> {
  return inFlight ?? fetchOnce()
}

/** Re-read the count *after* whatever is in flight, for callers that just
 * changed it.
 *
 * Returning the in-flight promise instead would make the re-poll a no-op
 * whenever the 30s timer happened to fire first: the request already on the
 * wire was issued before the decision, so it resolves with the pre-decision
 * count and the badge stays stale for another full interval — exactly what
 * deciding a review is supposed to clear.
 */
export function refreshMyReviewCount(): Promise<void> {
  return inFlight ? inFlight.then(fetchOnce) : fetchOnce()
}

export function useMyReviewCount() {
  const [count, setCount] = useState<number>(cached ?? 0)

  useEffect(() => {
    subscribers.add(setCount)
    void refresh()
    if (!timer) timer = setInterval(() => void refresh(), POLL_MS)
    return () => {
      subscribers.delete(setCount)
      if (subscribers.size === 0 && timer) {
        clearInterval(timer)
        timer = null
      }
    }
  }, [])

  // The only callers of this are surfaces that have *just* decided a review,
  // so they get the variant that re-reads after any in-flight poll rather than
  // adopting its pre-decision answer.
  return { count, refresh: refreshMyReviewCount }
}
