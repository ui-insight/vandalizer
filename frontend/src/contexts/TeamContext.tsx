import { createContext, useCallback, useEffect, useState, type ReactNode } from 'react'
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
  const { user } = useAuth()
  const [teams, setTeams] = useState<Team[]>([])
  const [loading, setLoading] = useState(true)

  const refreshTeams = useCallback(async () => {
    if (!user) {
      setTeams([])
      setLoading(false)
      return
    }
    try {
      const data = await teamsApi.listTeams()
      setTeams(data)
    } catch {
      setTeams([])
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => {
    refreshTeams()
  }, [refreshTeams])

  const currentTeam = teams.find((t) => t.uuid === user?.current_team_uuid) ?? teams[0] ?? null

  const switchTeam = useCallback(
    async (teamUuid: string) => {
      await teamsApi.switchTeam(teamUuid)
      // Reload page to refresh all state
      window.location.reload()
    },
    [],
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
      value={{ teams, currentTeam, loading, switchTeam, createTeam, refreshTeams }}
    >
      {children}
    </TeamContext.Provider>
  )
}
