import { useEffect, useRef, useState, useCallback } from 'react'
import { getActiveAutomations, type CompletedAutomation } from '../api/automations'
import { listAutomations } from '../api/automations'

const POLL_INTERVAL = 10_000

export interface AutomationStarted {
  id: string
  name: string
}

export function useAutomationActivity(
  onStarted?: (info: AutomationStarted) => void,
  onCompleted?: (info: CompletedAutomation) => void,
) {
  const [activeIds, setActiveIds] = useState<Set<string>>(new Set())
  const prevActiveRef = useRef<Set<string>>(new Set())
  const seenCompletedRef = useRef<Set<string>>(new Set())
  const automationNamesRef = useRef<Map<string, string>>(new Map())
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const onStartedRef = useRef(onStarted)
  const onCompletedRef = useRef(onCompleted)
  onStartedRef.current = onStarted
  onCompletedRef.current = onCompleted

  // Periodically refresh automation names so we can label "started" toasts
  const refreshNames = useCallback(async () => {
    try {
      const list = await listAutomations()
      const map = new Map<string, string>()
      for (const a of list) map.set(a.id, a.name)
      automationNamesRef.current = map
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    let cancelled = false
    let isFirstPoll = true

    // Fetch names once on mount
    refreshNames()

    const poll = async () => {
      try {
        const data = await getActiveAutomations()
        if (cancelled) return

        const newActive = new Set(data.active_automation_ids)

        if (!isFirstPoll) {
          const prev = prevActiveRef.current

          // Detect newly started automations
          for (const id of newActive) {
            if (!prev.has(id)) {
              const name = automationNamesRef.current.get(id) || 'Automation'
              onStartedRef.current?.({ id, name })
            }
          }

          // Detect recently completed automations from backend
          for (const rc of data.recently_completed || []) {
            if (!seenCompletedRef.current.has(rc.id)) {
              seenCompletedRef.current.add(rc.id)
              onCompletedRef.current?.(rc)
              // Clear from seen after 60s to allow re-triggering
              setTimeout(() => seenCompletedRef.current.delete(rc.id), 60_000)
            }
          }
        } else {
          // On first poll, seed the seen-completed set so we don't toast stale completions
          for (const rc of data.recently_completed || []) {
            seenCompletedRef.current.add(rc.id)
          }
        }

        isFirstPoll = false
        prevActiveRef.current = newActive
        setActiveIds(newActive)
      } catch {
        // silently ignore polling errors
      }
    }

    poll()
    timerRef.current = setInterval(poll, POLL_INTERVAL)

    // Refresh names periodically (every 60s)
    const namesTimer = setInterval(refreshNames, 60_000)

    return () => {
      cancelled = true
      if (timerRef.current) clearInterval(timerRef.current)
      clearInterval(namesTimer)
    }
  }, [refreshNames])

  return { activeIds, hasActive: activeIds.size > 0 }
}
