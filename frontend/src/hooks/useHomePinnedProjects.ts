import { useCallback, useSyncExternalStore } from 'react'

/**
 * Projects pinned to Home, per browser (#1014 item 58). A handful of the
 * proposals or awards someone works on every day, one click from Home — not
 * a second project list. Kept in localStorage like Home's other display
 * choices; a pin to a project the viewer can no longer open simply doesn't
 * render, because Home shows only pins that match a listed project.
 */
const KEY = 'vandalizer:home:pinned-projects'
export const MAX_HOME_PINS = 5

const listeners = new Set<() => void>()
let memory: string[] = []

function read(): string[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) || '[]')
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === 'string') : []
  } catch {
    return memory
  }
}

// useSyncExternalStore needs a stable snapshot between changes.
let snapshot: string[] | null = null
function getSnapshot(): string[] {
  if (snapshot === null) snapshot = read()
  return snapshot
}

function write(next: string[]) {
  memory = next
  try { localStorage.setItem(KEY, JSON.stringify(next)) } catch { /* the in-memory copy keeps this page right */ }
  snapshot = next
  listeners.forEach(l => l())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY) { snapshot = null; listener() }
  }
  window.addEventListener('storage', onStorage)
  return () => { listeners.delete(listener); window.removeEventListener('storage', onStorage) }
}

export function useHomePinnedProjects() {
  const pinned = useSyncExternalStore(subscribe, getSnapshot)
  const isPinned = useCallback((uuid: string) => pinned.includes(uuid), [pinned])
  /** Returns false when the pin limit is reached. */
  const togglePin = useCallback((uuid: string): boolean => {
    const current = getSnapshot()
    if (current.includes(uuid)) { write(current.filter(u => u !== uuid)); return true }
    if (current.length >= MAX_HOME_PINS) return false
    write([...current, uuid])
    return true
  }, [])
  return { pinned, isPinned, togglePin }
}

/** Test hook: forget the cached snapshot after localStorage is reset. */
export function resetHomePinnedProjectsForTests() {
  snapshot = null
  memory = []
}
