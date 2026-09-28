import { useCallback, useEffect, useRef, useState } from 'react'
import { updateAutomation } from '../api/automations'
import type { Automation } from '../types/automation'

type Updates = Parameters<typeof updateAutomation>[1]
type SaveState = 'saved' | 'pending' | 'saving' | 'error'

/** Combine debounced edits and serialize writes so older responses cannot win. */
export function useAutomationSave(id: string | null, onSaved: (automation: Automation) => void) {
  const [state, setState] = useState<SaveState>('saved')
  const [error, setError] = useState<string | null>(null)
  const pending = useRef<Updates>({})
  const inFlight = useRef<Promise<boolean> | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mounted = useRef(true)
  const onSavedRef = useRef(onSaved)
  onSavedRef.current = onSaved

  const flush = useCallback((): Promise<boolean> => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null }
    if (inFlight.current) return inFlight.current
    if (!id || !Object.keys(pending.current).length) return Promise.resolve(true)
    const drain = async () => {
      if (mounted.current) { setState('saving'); setError(null) }
      while (Object.keys(pending.current).length) {
        const batch = pending.current
        pending.current = {}
        try {
          const saved = await updateAutomation(id, batch)
          if (mounted.current) onSavedRef.current({ ...saved, ...pending.current } as Automation)
          window.dispatchEvent(new Event('automations-updated'))
        } catch (reason) {
          if (timer.current) { clearTimeout(timer.current); timer.current = null }
          pending.current = { ...batch, ...pending.current }
          if (mounted.current) {
            setState('error')
            setError(reason instanceof Error ? reason.message : 'Could not save changes.')
          }
          return false
        }
      }
      if (mounted.current) setState('saved')
      return true
    }
    inFlight.current = drain().finally(() => { inFlight.current = null })
    return inFlight.current
  }, [id])

  const save = useCallback((updates: Updates, debounce = false) => {
    pending.current = { ...pending.current, ...updates }
    if (timer.current) clearTimeout(timer.current)
    if (!debounce) return flush()
    setState('pending')
    setError(null)
    timer.current = setTimeout(() => { void flush() }, 500)
    return Promise.resolve(true)
  }, [flush])

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      // Navigating away during the debounce must not silently discard edits.
      void flush()
    }
  }, [flush])

  return { save, flush, state, error }
}
