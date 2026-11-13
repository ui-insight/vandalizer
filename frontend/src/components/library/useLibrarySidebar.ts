import { useCallback, useEffect, useState } from 'react'

/** Whether the Library's views-and-folders sidebar is collapsed.
 *
 * UI suggestion ticket: the sidebar took a third of the panel for people
 * with no folders, where it held only All items, Favorites, Pinned and "No
 * folders yet", and squeezed the tool list.
 *
 * - Once the person collapses or expands it, that choice is kept (in this
 *   browser) and always wins.
 * - Until then it follows the folders in the scope being shown (Mine or
 *   Team): collapsed with none, expanded with some. So creating a first
 *   folder expands it, and an error loading folders keeps it open so the
 *   Retry is visible.
 * - While folders load, the scope and team's last known state is used, so the
 *   sidebar doesn't open and then snap shut on every visit.
 */

export type SidebarPreference = 'collapsed' | 'expanded'

export const PREFERENCE_KEY = 'library:sidebar'
// Folders are listed per scope and team, so the hint is too.
export const hasFoldersKey = (scope: string, teamId?: string) => `library:hasFolders:${scope}:${teamId ?? 'none'}`

// Storage can be unavailable (private windows, blocked site data): the
// sidebar still works, it just isn't remembered.
export function readStored(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}
export function writeStored(key: string, value: string) {
  try { localStorage.setItem(key, value) } catch { /* not remembered */ }
}

interface Folders {
  scope: string
  teamId?: string
  folderCount: number
  loading: boolean
  error: boolean
}

export function useLibrarySidebar({ scope, teamId, folderCount, loading, error }: Folders) {
  const [preference, setPreference] = useState<SidebarPreference | null>(() => {
    const stored = readStored(PREFERENCE_KEY)
    return stored === 'collapsed' || stored === 'expanded' ? stored : null
  })
  const settled = !loading && !error
  useEffect(() => {
    if (settled) writeStored(hasFoldersKey(scope, teamId), folderCount > 0 ? '1' : '0')
  }, [scope, teamId, settled, folderCount])

  const automatic = error ? false
    : loading ? readStored(hasFoldersKey(scope, teamId)) !== '1'
    : folderCount === 0
  const collapsed = preference ? preference === 'collapsed' : automatic

  const setCollapsed = useCallback((next: boolean) => {
    const value: SidebarPreference = next ? 'collapsed' : 'expanded'
    writeStored(PREFERENCE_KEY, value)
    setPreference(value)
  }, [])

  return { collapsed, setCollapsed, remembered: preference !== null }
}
