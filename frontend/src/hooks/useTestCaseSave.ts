import { useCallback, useRef, useState } from 'react'
import { updateTestCase } from '../api/extractions'

type Patch = Parameters<typeof updateTestCase>[1]

/** Serialize edits per source so a slow earlier request cannot overwrite a newer answer. */
export function useTestCaseSave() {
  const pending = useRef(new Map<string, Patch>())
  const running = useRef(new Map<string, Promise<boolean>>())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const flush = useCallback((id: string): Promise<boolean> => {
    const active = running.current.get(id)
    if (active) return active
    const run = async () => {
      // Defer until the promise has been registered, including synchronous mocks.
      await Promise.resolve()
      setSaving(true)
      try {
        while (pending.current.has(id)) {
          const patch = pending.current.get(id)!
          pending.current.delete(id)
          try {
            await updateTestCase(id, patch)
          } catch (reason) {
            pending.current.set(id, { ...patch, ...pending.current.get(id) })
            setError(`Test-case changes are not saved. ${reason instanceof Error ? reason.message : 'Please retry.'} Your edits are kept here.`)
            return false
          }
        }
        return true
      } finally {
        running.current.delete(id)
        setSaving(running.current.size > 0)
        if (running.current.size === 0 && pending.current.size === 0) setError(null)
      }
    }
    const result = run()
    running.current.set(id, result)
    return result
  }, [])

  const save = useCallback((id: string, patch: Patch) => {
    pending.current.set(id, { ...pending.current.get(id), ...patch })
    return flush(id)
  }, [flush])

  const retry = useCallback(async () => {
    const ids = new Set([...pending.current.keys(), ...running.current.keys()])
    const results = await Promise.all([...ids].map(flush))
    return results.every(Boolean)
  }, [flush])

  return { save, retry, saving, error }
}
