import { useCallback, useEffect, useRef, useState } from 'react'
import { listAllFolders } from '../api/folders'
import { useTeams } from './useTeams'

/** Resolve names once per surface, never one request for each automation card. */
export function useAutomationFolderNames() {
  const { currentTeam } = useTeams()
  const team = currentTeam?.uuid ?? null
  const [snapshot, setSnapshot] = useState<{ team: string | null; folders: { uuid: string; path: string }[] }>({ team: null, folders: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const request = useRef(0)
  const refresh = useCallback(async () => {
    const version = ++request.current
    setLoading(true); setError(null)
    try {
      const folders = await listAllFolders()
      if (version === request.current) setSnapshot({ team, folders })
    } catch (reason) {
      if (version === request.current) setError(reason instanceof Error ? reason.message : 'Could not load folder names.')
    } finally { if (version === request.current) setLoading(false) }
  }, [team])
  useEffect(() => { void refresh(); return () => { request.current += 1 } }, [refresh])
  return { folders: snapshot.team === team ? snapshot.folders : [], loading, error, refresh }
}
