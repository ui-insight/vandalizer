import { useContext } from 'react'
import { TeamContext } from '../contexts/TeamContext'

export function useTeams() {
  const ctx = useContext(TeamContext)
  if (!ctx) throw new Error('useTeams must be used within TeamProvider')
  return ctx
}
