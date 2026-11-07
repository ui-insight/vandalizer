import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { TeamProvider } from './TeamContext'
import { useTeams } from '../hooks/useTeams'
import type { Team, User } from '../types/user'
const mocks = vi.hoisted(() => ({ user: null as User | null, list: vi.fn(), refresh: vi.fn() }))
vi.mock('../hooks/useAuth', () => ({ useAuth: () => ({ user: mocks.user, refreshUser: mocks.refresh }) }))
vi.mock('../api/teams', () => ({ listTeams: mocks.list }))
beforeEach(() => { vi.clearAllMocks(); mocks.user = null })
it('reports loading until teams for the signed-in user have resolved', async () => {
  const { result, rerender } = renderHook(() => useTeams(), { wrapper: TeamProvider })
  expect(result.current.loading).toBe(false)
  let finish!: (value: Team[]) => void
  mocks.list.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  mocks.user = { user_id: 'u1' } as User; rerender()
  expect(result.current.loading).toBe(true)
  await act(async () => { finish([{ uuid: 't1' } as Team]) })
  expect(result.current.loading).toBe(false)
  expect(result.current.currentTeam?.uuid).toBe('t1')
})
it('ignores an earlier team response that arrives after an account change', async () => {
  let first!: (value: Team[]) => void
  mocks.user = { user_id: 'u1' } as User
  mocks.list.mockImplementationOnce(() => new Promise(resolve => { first = resolve }))
  const { result, rerender } = renderHook(() => useTeams(), { wrapper: TeamProvider })
  mocks.list.mockResolvedValue([{ uuid: 't2' } as Team]); mocks.user = { user_id: 'u2' } as User; rerender()
  await waitFor(() => expect(result.current.currentTeam?.uuid).toBe('t2'))
  await act(async () => { first([{ uuid: 't1' } as Team]) })
  expect(result.current.currentTeam?.uuid).toBe('t2')
  expect(result.current.loading).toBe(false)
})

it('keeps same-account team context on refresh failure but never reveals it to another account', async () => {
  mocks.user = { user_id: 'u1' } as User
  mocks.list.mockResolvedValueOnce([{ uuid: 't1' } as Team])
  const { result, rerender } = renderHook(() => useTeams(), { wrapper: TeamProvider })
  await waitFor(() => expect(result.current.currentTeam?.uuid).toBe('t1'))
  mocks.list.mockRejectedValue(new Error('Unavailable'))
  await act(async () => { await result.current.refreshTeams() })
  expect(result.current.currentTeam?.uuid).toBe('t1')
  expect(result.current.error).toBe('Unavailable')
  mocks.user = { user_id: 'u2' } as User; rerender()
  expect(result.current.teams).toEqual([])
  await waitFor(() => expect(result.current.loading).toBe(false))
  expect(result.current.currentTeam).toBeNull()
  expect(result.current.teams).toEqual([])
})
