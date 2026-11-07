import type { Automation } from '../../types/automation'
import { parseServerTimestamp } from '../../utils/time'

export type AutomationStatus = 'running' | 'active' | 'paused'

/** What the row's status pill says. The dot alone (green/grey/pulsing yellow)
 *  left users guessing, so the state is always named. */
export const AUTOMATION_STATUS: Record<AutomationStatus, { label: string; color: string; bg: string; title: string }> = {
  running: { label: 'Running', color: '#854d0e', bg: 'rgba(234, 179, 8, 0.12)', title: 'Running right now' },
  active: { label: 'Active', color: '#166534', bg: 'rgba(34, 197, 94, 0.12)', title: 'On — runs when its trigger fires' },
  paused: { label: 'Paused', color: '#4b5563', bg: 'rgba(107, 114, 128, 0.18)', title: 'Off — its trigger is ignored until you turn it back on' },
}

export function automationStatus(auto: Automation, isRunning: boolean): AutomationStatus {
  if (isRunning) return 'running'
  return auto.enabled ? 'active' : 'paused'
}

export type AutomationSort = 'updated' | 'newest' | 'name' | 'status'

export const AUTOMATION_SORT_OPTIONS: [AutomationSort, string][] = [
  ['updated', 'Recently updated'],
  ['newest', 'Newest'],
  ['name', 'Name A-Z'],
  ['status', 'Status'],
]

const STATUS_ORDER: Record<AutomationStatus, number> = { running: 0, active: 1, paused: 2 }

const time = (iso: string | null | undefined) => {
  const t = iso ? parseServerTimestamp(iso).getTime() : NaN
  return Number.isNaN(t) ? 0 : t
}

const byName = (a: Automation, b: Automation) =>
  a.name.localeCompare(b.name, undefined, { sensitivity: 'base', numeric: true })

/** A sorted copy. Ties fall back to name so the order is stable across refreshes. */
export function sortAutomations(
  list: Automation[], sort: AutomationSort, activeIds: Set<string> = new Set(),
): Automation[] {
  const out = [...list]
  switch (sort) {
    case 'name':
      return out.sort(byName)
    case 'newest':
      return out.sort((a, b) => time(b.created_at) - time(a.created_at) || byName(a, b))
    case 'status':
      return out.sort((a, b) =>
        STATUS_ORDER[automationStatus(a, activeIds.has(a.id))] - STATUS_ORDER[automationStatus(b, activeIds.has(b.id))]
        || byName(a, b))
    case 'updated':
    default:
      return out.sort((a, b) => time(b.updated_at) - time(a.updated_at) || byName(a, b))
  }
}

const SORT_KEY = 'automations.sort'

export function loadAutomationSort(): AutomationSort {
  try {
    const v = localStorage.getItem(SORT_KEY)
    if (v && AUTOMATION_SORT_OPTIONS.some(([k]) => k === v)) return v as AutomationSort
  } catch { /* storage unavailable: use the default */ }
  return 'updated'
}

export function saveAutomationSort(sort: AutomationSort): void {
  try { localStorage.setItem(SORT_KEY, sort) } catch { /* not remembered; harmless */ }
}
