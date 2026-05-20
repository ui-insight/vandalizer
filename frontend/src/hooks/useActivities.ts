import { useState, useEffect, useCallback, useRef } from 'react'
import { listActivities } from '../api/activity'
import type { ActivityEvent } from '../types/chat'

const POLL_INTERVAL = 3000
const DEFAULT_STALE_THRESHOLD_MINUTES = 30

export function useActivities(externalSignal?: number) {
  const [activities, setActivities] = useState<ActivityEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [freshTitleIds, setFreshTitleIds] = useState<Set<string>>(new Set())
  const [staleThresholdMinutes, setStaleThresholdMinutes] = useState<number>(
    DEFAULT_STALE_THRESHOLD_MINUTES,
  )
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const prevRef = useRef<Map<string, string>>(new Map())
  const lastActiveAtRef = useRef<number>(0)
  // Hard upper bound on tail polling — ensures we stop eventually if the
  // title generator silently fails (e.g. no model configured).
  const TAIL_DURATION = 120000

  const markTitleShimmered = useCallback((id: string) => {
    setFreshTitleIds((prev) => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })
  }, [])

  const refresh = useCallback(async () => {
    try {
      const data = await listActivities(50)
      const newActivities = data.events

      // Detect AI-title arrival on completed activities. Track via the
      // description_generated flag rather than title-string diffs so we
      // also catch the case where the AI title happens to equal the
      // placeholder.
      const prevMap = prevRef.current
      const changedIds: string[] = []
      for (const activity of newActivities) {
        const generated = (activity.meta_summary as { description_generated?: boolean } | undefined)
          ?.description_generated === true
        const prevKey = prevMap.get(activity.id)
        const wasGenerated = prevKey?.startsWith('gen:') ?? false
        if (
          prevMap.has(activity.id) &&
          activity.status === 'completed' &&
          activity.title &&
          generated &&
          !wasGenerated
        ) {
          changedIds.push(activity.id)
        }
      }

      // Encode both "have we seen this id" and "was the AI title in" in
      // one map value so the next refresh can detect the gen:false → gen:true
      // transition without a second ref.
      prevRef.current = new Map(
        newActivities.map((a) => {
          const generated = (a.meta_summary as { description_generated?: boolean } | undefined)
            ?.description_generated === true
          return [a.id, `${generated ? 'gen' : 'pre'}:${a.title ?? ''}`]
        }),
      )
      setActivities(newActivities)

      if (typeof data.stale_threshold_minutes === 'number' && data.stale_threshold_minutes > 0) {
        setStaleThresholdMinutes(data.stale_threshold_minutes)
      }

      if (changedIds.length > 0) {
        setFreshTitleIds((prev) => {
          const next = new Set(prev)
          changedIds.forEach((id) => next.add(id))
          return next
        })
      }
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial fetch + re-fetch on external signal.
  // Signal bumps mean "something was just kicked off" — enter the tail window
  // so polling runs even before the activity record is visible. Avoids a race
  // where the first refresh lands before the backend has created the record.
  useEffect(() => {
    refresh()
    if (externalSignal !== undefined) {
      lastActiveAtRef.current = Date.now()
    }
  }, [refresh, externalSignal])

  // Poll while active, then keep polling until every recently-completed
  // activity has its AI title (or we hit the TAIL_DURATION cap). The AI
  // title is written by Celery after completion and can take 5–30s on slow
  // models, so we can't use a fixed short tail.
  useEffect(() => {
    const hasActive = activities.some(
      (a) => a.status === 'running' || a.status === 'queued',
    )

    if (hasActive) {
      lastActiveAtRef.current = Date.now()
    }

    const sinceActive = Date.now() - lastActiveAtRef.current
    const inTail = sinceActive < TAIL_DURATION
    // Keep polling if any completed activity in the recent window is still
    // waiting on its AI-generated title.
    const awaitingTitle = inTail && activities.some((a) => {
      if (a.status !== 'completed') return false
      const generated = (a.meta_summary as { description_generated?: boolean } | undefined)
        ?.description_generated
      return !generated
    })
    const shouldPoll = hasActive || awaitingTitle

    if (shouldPoll) {
      if (!pollRef.current) {
        pollRef.current = setInterval(refresh, POLL_INTERVAL)
      }
    } else {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [activities, refresh])

  return {
    activities,
    loading,
    refresh,
    freshTitleIds,
    markTitleShimmered,
    staleThresholdMinutes,
  }
}
