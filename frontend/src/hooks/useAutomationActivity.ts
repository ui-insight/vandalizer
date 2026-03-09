import { useEffect, useRef, useState } from 'react'
import { getActiveAutomations } from '../api/automations'

const POLL_INTERVAL = 10_000

export function useAutomationActivity() {
  const [activeIds, setActiveIds] = useState<Set<string>>(new Set())
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    let cancelled = false

    const poll = async () => {
      try {
        const data = await getActiveAutomations()
        if (!cancelled) {
          setActiveIds(new Set(data.active_automation_ids))
        }
      } catch {
        // silently ignore polling errors
      }
    }

    poll()
    timerRef.current = setInterval(poll, POLL_INTERVAL)

    return () => {
      cancelled = true
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [])

  return { activeIds, hasActive: activeIds.size > 0 }
}
