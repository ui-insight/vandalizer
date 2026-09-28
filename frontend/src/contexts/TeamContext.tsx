import { createContext, useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import type { Team } from '../types/user'
import * as teamsApi from '../api/teams'
import { useAuth } from '../hooks/useAuth'

interface TeamContextValue {
  teams: Team[]
  currentTeam: Team | null
  loading: boolean
  switchTeam: (teamUuid: string) => Promise<void>
  createTeam: (name: string) => Promise<void>
  refreshTeams: () => Promise<void>
}

export const TeamContext = createContext<TeamContextValue | null>(null)

export function TeamProvider({ children }: { children: ReactNode }) {
  const { user, refreshUser } = useAuth()
  const [teams, setTeams] = useState<Team[]>([])
  const [loading, setLoading] = useState(true)
  const [loadedUserId, setLoadedUserId] = useState<string | null>(null)
  const requestVersion = useRef(0)

  const refreshTeams = useCallback(async () => {
    const version = ++requestVersion.current
    if (!user) {
      setTeams([])
      setLoadedUserId(null)
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const data = await teamsApi.listTeams()
      if (version === requestVersion.current) setTeams(data)
    } catch {
      if (version === requestVersion.current) setTeams([])
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

  const currentTeam = teams.find((t) => t.uuid === user?.current_team_uuid) ?? teams[0] ?? null

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
      value={{ teams, currentTeam, loading: loading || loadedUserId !== (user?.user_id ?? null), switchTeam, createTeam, refreshTeams }}
    >
      {children}
    </TeamContext.Provider>
  )
}
