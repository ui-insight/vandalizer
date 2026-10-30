import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { updateAutomation } from '../api/automations'
import type { Automation } from '../types/automation'

type Updates = Parameters<typeof updateAutomation>[1]
type SaveState = 'saved' | 'pending' | 'saving' | 'error'
type Listener = (saved?: Automation) => void

// Keep drafts in this tab's memory: output settings may contain credentials.
// A shared queue survives panel navigation and serializes old/new editor writes.
const sessions = new Map<string, ReturnType<typeof createSession>>()
function createSession(id: string | null) {
  let pending: Updates = {}, sending: Updates = {}
  let inFlight: Promise<boolean> | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  let state: SaveState = 'saved', error: string | null = null
  let revision = 0, latest: Automation | null = null
  const listeners = new Set<Listener>()
  const emit = (saved?: Automation) => listeners.forEach(listener => listener(saved))
  const stopTimer = () => { if (timer) clearTimeout(timer); timer = null }
  const overlay = (value: Automation) => ({ ...value, ...sending, ...pending } as Automation)
  const flush = (): Promise<boolean> => {
    stopTimer()
    if (inFlight) return inFlight
    if (!id || !Object.keys(pending).length) return Promise.resolve(true)
    state = 'saving'; error = null; emit()
    const drain = async () => {
      while (Object.keys(pending).length) {
        sending = pending; pending = {}
        try {
          latest = await updateAutomation(id, sending)
          revision++
          sending = {}
          emit(overlay(latest))
          window.dispatchEvent(new Event('automations-updated'))
        } catch (reason) {
          stopTimer()
          pending = { ...sending, ...pending }; sending = {}
          state = 'error'
          error = reason instanceof Error ? reason.message : 'Could not save changes.'
          emit()
          return false
        }
      }
      state = 'saved'; emit()
      return true
    }
    inFlight = drain().finally(() => { inFlight = null })
    return inFlight
  }
  return {
    flush,
    snapshot: () => ({ state, error }),
    revision: () => revision,
    // A GET begun before our PATCH completed must not overwrite its response.
    applyLoaded: (value: Automation, startedAt: number) => value.can_manage === false
      ? value : overlay(revision > startedAt && latest ? { ...latest, can_manage: value.can_manage } : value),
    subscribe(listener: Listener) { listeners.add(listener); return () => { listeners.delete(listener) } },
    save(updates: Updates, debounce = false) {
      pending = { ...pending, ...updates }; stopTimer()
      if (!debounce) return flush()
      state = inFlight ? 'saving' : 'pending'; error = null; emit()
      timer = setTimeout(() => { void flush() }, 500)
      return Promise.resolve(true)
    },
    leave() {
      // Failed requests require an explicit retry; navigation must not resubmit.
      if (state === 'pending') void flush()
    },
  }
}

/** Combine edits and retain unsuccessful writes across navigation in this tab. */
export function useAutomationSave(id: string | null, onSaved: (automation: Automation) => void, userScope?: string) {
  const session = useMemo(() => {
    if (!userScope || !id) return createSession(id)
    const key = JSON.stringify([userScope, id])
    let existing = sessions.get(key)
    if (!existing) { existing = createSession(id); sessions.set(key, existing) }
    return existing
  }, [id, userScope])
  const [snapshot, setSnapshot] = useState(session.snapshot)
  const onSavedRef = useRef(onSaved)
  onSavedRef.current = onSaved
  useEffect(() => {
    setSnapshot(session.snapshot())
    const unsubscribe = session.subscribe(saved => {
      setSnapshot(session.snapshot())
      if (saved) onSavedRef.current(saved)
    })
    return () => { unsubscribe(); session.leave() }
  }, [session])
  const save = useCallback((updates: Updates, debounce = false) => session.save(updates, debounce), [session])
  return { save, flush: session.flush, revision: session.revision, applyLoaded: session.applyLoaded, ...snapshot }
}
