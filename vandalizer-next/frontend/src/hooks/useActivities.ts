import { useState, useEffect, useCallback, useRef } from 'react'
import { listActivities } from '../api/activity'
import type { ActivityEvent } from '../types/chat'

const POLL_INTERVAL = 3000

export function useActivities() {
  const [activities, setActivities] = useState<ActivityEvent[]>([])
  const [loading, setLoading] = useState(true)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const refresh = useCallback(async () => {
    try {
      const data = await listActivities(50)
      setActivities(data.events)
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial fetch
  useEffect(() => {
    refresh()
  }, [refresh])

  // Auto-poll when there are running/queued activities
  useEffect(() => {
    const hasActive = activities.some(
      (a) => a.status === 'running' || a.status === 'queued',
    )

    if (hasActive) {
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

  return { activities, loading, refresh }
}
