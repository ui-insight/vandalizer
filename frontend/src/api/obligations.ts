import { apiFetch, rawFetch } from './client'

/** One place a claim comes from: a document, a page, the exact passage. */
export interface ObligationSource {
  document_uuid: string
  document_title: string
  page: number | null
  quote: string
  role: string
}

/** A deadline, required piece of material or sponsor limit from a project's documents (#999). */
export interface Obligation {
  uuid: string
  project_uuid: string
  project_title: string | null
  kind: 'deadline' | 'required_material' | 'limit'
  title: string
  deadline_type: string | null
  due_at: string | null
  due_text: string | null
  deadline_calculation?: {
    rule: string
    anchor_kind: string
    anchor_date: string
    offset_days: number
    formula: string
  } | null
  limit_value: number | null
  observed_value: number | null
  unit: string | null
  in_conflict: boolean
  sources: ObligationSource[]
  status: 'open' | 'done' | 'superseded'
  supersedes: string | null
  superseded_by: string | null
  /** Hidden from this user's Home; teammates still see it. */
  dismissed: boolean
}

/** Home's list across your projects, or one project's when *projectUuid* is given. */
export function getInbox(includeDismissed = false, projectUuid?: string | null) {
  const query = new URLSearchParams()
  if (includeDismissed) query.set('include_dismissed', 'true')
  if (projectUuid) query.set('project_uuid', projectUuid)
  const search = query.toString()
  return apiFetch<{ items: Obligation[]; inbox_hidden: boolean; project_count?: number }>(
    `/api/obligations${search ? `?${search}` : ''}`,
  )
}

export function setObligationDone(uuid: string, done: boolean) {
  return apiFetch<Obligation>(`/api/obligations/${uuid}/done`, { method: 'POST', body: JSON.stringify({ done }) })
}

export function setObligationDismissed(uuid: string, dismissed: boolean) {
  return apiFetch<Obligation>(`/api/obligations/${uuid}/dismiss`, { method: 'POST', body: JSON.stringify({ dismissed }) })
}

export function setInboxHidden(inboxHidden: boolean) {
  return apiFetch<{ inbox_hidden: boolean }>('/api/obligations/home-settings', {
    method: 'PUT',
    body: JSON.stringify({ inbox_hidden: inboxHidden }),
  })
}

export function getObligation(uuid: string) {
  return apiFetch<Obligation>(`/api/obligations/${encodeURIComponent(uuid)}`)
}

/** A source quote as people read it: quotes match the document's extracted
 * text, which can keep table markup (`<td>Period of Performance</td>…`). */
export function plainQuote(quote: string): string {
  const text = quote.replace(/<[^>]+>/g, ' ')
  const decoded = new DOMParser().parseFromString(text, 'text/html').documentElement.textContent ?? text
  return decoded.split(/\s+/).filter(Boolean).join(' ')
}

/** The words the document viewer highlights for a source quote. */
export function quoteSearchTerms(quote: string): string {
  return plainQuote(quote).split(' ').slice(0, 8).join(' ')
}

export interface ReminderSettings {
  bell: boolean
  email: boolean
  /** Days before the due date to remind, largest first (e.g. [14, 3]). */
  days_before: number[]
  on_due: boolean
  overdue: boolean
  weekly_summary: boolean
  /** Team admins: also remind about every project of their teams. */
  team_projects: boolean
}

export function getReminderSettings() {
  return apiFetch<{ settings: ReminderSettings; team_admin: boolean }>('/api/obligations/reminder-settings')
}

export function updateReminderSettings(changes: Partial<ReminderSettings>) {
  return apiFetch<{ settings: ReminderSettings; team_admin: boolean }>('/api/obligations/reminder-settings', {
    method: 'PUT',
    body: JSON.stringify(changes),
  })
}

/** Download a calendar file: one deadline, one project's deadlines, or all of yours. */
export async function downloadDeadlineCalendar(target: { obligation: string } | { project: string } | 'all'): Promise<void> {
  const url = target === 'all' ? '/api/obligations/calendar.ics'
    : 'obligation' in target ? `/api/obligations/${encodeURIComponent(target.obligation)}/calendar.ics`
      : `/api/obligations/calendar.ics?project_uuid=${encodeURIComponent(target.project)}`
  const res = await rawFetch(url)
  if (!res.ok) throw new Error(res.status === 400 ? 'Only a deadline with a date can be added to a calendar.' : 'The calendar file could not be downloaded.')
  const name = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') ?? '')?.[1] ?? 'deadlines.ics'
  const href = URL.createObjectURL(await res.blob())
  const link = document.createElement('a')
  link.href = href
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(href)
}
