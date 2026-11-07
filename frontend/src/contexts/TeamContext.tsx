import { createContext, useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import type { Team } from '../types/user'
import * as teamsApi from '../api/teams'
import { useAuth } from '../hooks/useAuth'

interface TeamContextValue {
  teams: Team[]
  currentTeam: Team | null
  loading: boolean
  error?: string | null
  switchTeam: (teamUuid: string) => Promise<void>
  createTeam: (name: string) => Promise<void>
  refreshTeams: () => Promise<void>
}

export const TeamContext = createContext<TeamContextValue | null>(null)

export function TeamProvider({ children }: { children: ReactNode }) {
  const { user, refreshUser } = useAuth()
  const [teams, setTeams] = useState<Team[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [loadedUserId, setLoadedUserId] = useState<string | null>(null)
  const [dataUserId, setDataUserId] = useState<string | null>(null)
  const requestVersion = useRef(0)

  const refreshTeams = useCallback(async () => {
    const version = ++requestVersion.current
    setError(null)
    if (!user) {
      setTeams([])
      setDataUserId(null)
      setLoadedUserId(null)
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const data = await teamsApi.listTeams()
      if (version === requestVersion.current) { setTeams(data); setDataUserId(user.user_id) }
    } catch (reason) {
      if (version === requestVersion.current) setError(reason instanceof Error ? reason.message : 'Could not load teams.')
    } finally {
      if (version === requestVersion.current) {
        setLoadedUserId(user.user_id)
        setLoading(false)
      }
    }
  }, [user])

  useEffect(() => {
    refreshTeams()
  }, [refreshTeams])

  const visibleTeams = dataUserId === (user?.user_id ?? null) ? teams : []
  const currentTeam = visibleTeams.find((t) => t.uuid === user?.current_team_uuid) ?? visibleTeams[0] ?? null

  const switchTeam = useCallback(
    async (teamUuid: string) => {
      await teamsApi.switchTeam(teamUuid)
      // Refresh both user (for current_team_uuid) and teams list
      await Promise.all([refreshUser(), refreshTeams()])
    },
    [refreshUser, refreshTeams],
  )

  const createTeam = useCallback(
    async (name: string) => {
      await teamsApi.createTeam(name)
      await refreshTeams()
    },
    [refreshTeams],
  )

  return (
    <TeamContext.Provider
      value={{ teams: visibleTeams, currentTeam, error, loading: loading || loadedUserId !== (user?.user_id ?? null), switchTeam, createTeam, refreshTeams }}
    >
      {children}
    </TeamContext.Provider>
  )
}
