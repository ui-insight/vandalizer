/**
 * Where the open project was opened from, so Exit project can go back there.
 *
 * Support ticket: opening a project from the Projects list and clicking Exit
 * project landed on Home in chat (Files on the left, a new empty chat)
 * instead of back on the list. A project opened any other way (a chat, the
 * RA inbox, a link) still exits to Home.
 *
 * Session storage, keyed by the project's uuid: it survives a reload of the
 * open project, never leaks into another project, and ends with the tab.
 */
const KEY = 'workspace:project-opened-from-list'

/** The Projects list is opening this project. */
export function rememberOpenedFromProjects(uuid: string): void {
  try { sessionStorage.setItem(KEY, uuid) } catch { /* Exit falls back to Home. */ }
}

/** Whether this project was opened from the Projects list. */
export function openedFromProjects(uuid: string | null | undefined): boolean {
  if (!uuid) return false
  try { return sessionStorage.getItem(KEY) === uuid } catch { return false }
}

/** Forget the origin unless it belongs to *keepUuid* (the project now opening). */
export function forgetProjectOrigin(keepUuid?: string | null): void {
  try {
    if (!keepUuid || sessionStorage.getItem(KEY) !== keepUuid) sessionStorage.removeItem(KEY)
  } catch { /* Nothing stored. */ }
}
