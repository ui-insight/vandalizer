import { useCallback, useContext, useRef, useState, type SetStateAction } from 'react'
import { AuthContext } from '../contexts/AuthContext'

type Status = 'empty' | 'stored' | 'unavailable' | 'invalid'
type Draft<T> = { key: string | null; value: T; status: Status }
const MAX_BYTES = 200_000

export function courseDraftKey(userId: string, identity: readonly (string | null)[]) {
  return `cert-course-draft:${JSON.stringify([userId, ...identity])}`
}

function restore<T>(key: string, allowStorage: boolean, initial: T, valid: (value: unknown) => value is T): Draft<T> {
  if (!allowStorage) return { key, value: initial, status: 'unavailable' }
  try {
    const raw = sessionStorage.getItem(key)
    if (!raw) return { key, value: initial, status: 'empty' }
    if (raw.length > MAX_BYTES) return { key, value: initial, status: 'invalid' }
    const saved = JSON.parse(raw)
    return saved?.schema === 1 && valid(saved.value)
      ? { key, value: saved.value, status: 'stored' }
      : { key, value: initial, status: 'invalid' }
  } catch { return { key, value: initial, status: 'unavailable' } }
}

/** Tab-local authored input only. Never submits, restores consent to an API or awards credit. */
export function useCourseDraft<T>(identity: readonly (string | null)[], initial: T, valid: (value: unknown) => value is T) {
  const userId = useContext(AuthContext)?.user?.user_id
  const key = courseDraftKey(userId || '', identity)
  const [state, setState] = useState(() => restore(key, !!userId, initial, valid))
  // Reset during render so a changed user/course never paints the preceding draft.
  const current = state.key === key ? state : restore(key, !!userId, initial, valid)
  if (state.key !== key) setState(current)
  const latest = useRef(current)
  latest.current = current
  const setValue = useCallback((action: SetStateAction<T>) => {
    if (latest.current.key !== key) return // Ignore a callback retained by an old form.
    const value = typeof action === 'function' ? (action as (previous: T) => T)(latest.current.value) : action
    let status: Status = 'unavailable'
    if (userId) {
      try {
        const raw = JSON.stringify({ schema: 1, value })
        if (raw.length > MAX_BYTES) throw new Error('Draft exceeds tab storage limit')
        sessionStorage.setItem(key, raw)
        status = 'stored'
      } catch { /* Keep the current edit usable, and explain that it is not retained. */ }
    }
    const next = { key, value, status }
    latest.current = next
    setState(next)
  }, [key, userId])
  return [current.value, setValue, current.status] as const
}

export function draftStrings<K extends string>(keys: readonly K[], maxLength = 12000) {
  return (value: unknown): value is Record<K, string> => !!value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length
    && keys.every(key => typeof (value as Record<K, unknown>)[key] === 'string' && (value as Record<K, string>)[key].length <= maxLength)
}
