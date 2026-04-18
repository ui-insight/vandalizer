import { useState, useEffect, useCallback, useRef } from 'react'
import { listActivities } from '../api/activity'
import type { ActivityEvent } from '../types/chat'

const POLL_INTERVAL = 3000

export function useActivities(externalSignal?: number) {
  const [activities, setActivities] = useState<ActivityEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [freshTitleIds, setFreshTitleIds] = useState<Set<string>>(new Set())
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const prevRef = useRef<Map<string, string | null>>(new Map())
  const lastActiveAtRef = useRef<number>(0)
  const TAIL_DURATION = 15000 // keep polling 15s after completion for AI title

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

      // Detect title changes on completed activities — those just got an AI title
      const prevMap = prevRef.current
      const changedIds: string[] = []
      for (const activity of newActivities) {
        const prevTitle = prevMap.get(activity.id)
        if (
          prevMap.has(activity.id) &&
          prevTitle !== activity.title &&
          activity.title &&
          activity.status === 'completed'
        ) {
          changedIds.push(activity.id)
        }
      }

      prevRef.current = new Map(newActivities.map((a) => [a.id, a.title]))
      setActivities(newActivities)

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

  // Poll while active, then keep polling for TAIL_DURATION after completion
  // so the AI-generated title (written by Celery after the activity completes)
  // gets picked up.
  useEffect(() => {
    const hasActive = activities.some(
      (a) => a.status === 'running' || a.status === 'queued',
    )

    if (hasActive) {
      lastActiveAtRef.current = Date.now()
    }

    const inTail = Date.now() - lastActiveAtRef.current < TAIL_DURATION
    const shouldPoll = hasActive || inTail

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

  return { activities, loading, refresh, freshTitleIds, markTitleShimmered }
}
