import { useCallback, useEffect, useRef, useState } from 'react'

/** Keep the newest draft, serialize writes, and let a run await durable inputs. */
export function useValidationDraftSave<T>(persist: (draft: T) => Promise<unknown>) {
  const pending = useRef<{ value: T } | null>(null)
  const running = useRef<Promise<boolean> | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const flush = useCallback((): Promise<boolean> => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
    if (running.current) return running.current
    const work = async () => {
      await Promise.resolve()
      try {
        while (pending.current) {
          const draft = pending.current
          pending.current = null
          try {
            await persist(draft.value)
          } catch (reason) {
            pending.current ??= draft
            setError(reason instanceof Error ? reason.message : 'Please try again.')
            return false
          }
        }
        setError(null)
        return true
      } finally {
        running.current = null
        setSaving(false)
      }
    }
    running.current = work()
    return running.current
  }, [persist])

  const save = useCallback((value: T) => {
    pending.current = { value }
    setSaving(true)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => { void flush() }, 800)
  }, [flush])

  // Leaving the editor must not discard the debounce window's last edit.
  useEffect(() => () => { void flush() }, [flush])
  return { save, flush, saving, error }
}
