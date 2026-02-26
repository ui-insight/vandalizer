import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { UserPlus, Trash2 } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useTeams } from '../hooks/useTeams'
import { useAuth } from '../hooks/useAuth'
import type { TeamMember, TeamInvite } from '../types/user'
import {
  getTeamMembers,
  getTeamInvites,
  inviteMember,
  changeMemberRole,
  removeMember,
  createTeam,
} from '../api/teams'

export function TeamSettings() {
  const { user } = useAuth()
  const { teams, currentTeam, switchTeam, refreshTeams } = useTeams()
  const [members, setMembers] = useState<TeamMember[]>([])
  const [invites, setInvites] = useState<TeamInvite[]>([])
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState('member')
  const [newTeamName, setNewTeamName] = useState('')
  const [error, setError] = useState('')

  const canEdit = currentTeam?.role === 'owner' || currentTeam?.role === 'admin'

  const refreshData = useCallback(async () => {
    if (!currentTeam) return
    const [m, i] = await Promise.all([
      getTeamMembers(currentTeam.uuid),
      getTeamInvites(currentTeam.uuid),
    ])
    setMembers(m)
    setInvites(i)
  }, [currentTeam])

  useEffect(() => {
    refreshData()
  }, [refreshData])

  async function handleInvite(e: FormEvent) {
    e.preventDefault()
    if (!currentTeam || !inviteEmail.trim()) return
    setError('')
    try {
      await inviteMember(currentTeam.uuid, inviteEmail.trim(), inviteRole)
      setInviteEmail('')
      refreshData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to invite')
    }
  }

  async function handleRoleChange(userId: string, role: string) {
    if (!currentTeam) return
    try {
      await changeMemberRole(currentTeam.uuid, userId, role)
      refreshData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to change role')
    }
  }

  async function handleRemove(userId: string) {
    if (!currentTeam) return
    try {
      await removeMember(currentTeam.uuid, userId)
      refreshData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove member')
    }
  }

  async function handleCreateTeam(e: FormEvent) {
    e.preventDefault()
    if (!newTeamName.trim()) return
    await createTeam(newTeamName.trim())
    setNewTeamName('')
    refreshTeams()
  }

  return (
    <PageLayout>
      <div className="mx-auto max-w-3xl space-y-6">
        <h2 className="text-xl font-semibold text-gray-900">Teams</h2>

        {error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
        )}

        {/* Current team members */}
        {currentTeam && (
          <div className="rounded-lg border border-gray-200 bg-white">
            <div className="border-b border-gray-200 px-4 py-3">
              <h3 className="font-medium text-gray-900">{currentTeam.name}</h3>
              <p className="text-xs text-gray-500">Your role: {currentTeam.role}</p>
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-100 text-left">
                  <th className="px-4 py-2 text-xs font-medium uppercase text-gray-500">Member</th>
                  <th className="px-4 py-2 text-xs font-medium uppercase text-gray-500">Role</th>
                  {canEdit && <th className="w-20 px-4 py-2" />}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {members.map((m) => (
                  <tr key={m.user_id}>
                    <td className="px-4 py-3">
                      <div className="text-sm font-medium text-gray-900">
                        {m.name || m.user_id}
                      </div>
                      {m.email && <div className="text-xs text-gray-500">{m.email}</div>}
                    </td>
                    <td className="px-4 py-3">
                      {canEdit && m.user_id !== user?.user_id && m.role !== 'owner' ? (
                        <select
                          value={m.role}
                          onChange={(e) => handleRoleChange(m.user_id, e.target.value)}
                          className="rounded border border-gray-300 px-2 py-1 text-sm"
                        >
                          <option value="admin">admin</option>
                          <option value="member">member</option>
                        </select>
                      ) : (
                        <span className="text-sm text-gray-600">{m.role}</span>
                      )}
                    </td>
                    {canEdit && (
                      <td className="px-4 py-3">
                        {m.user_id !== user?.user_id && m.role !== 'owner' && (
                          <button
                            onClick={() => handleRemove(m.user_id)}
                            className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Invite form */}
        {canEdit && (
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <h3 className="mb-3 font-medium text-gray-900">Invite Member</h3>
            <form onSubmit={handleInvite} className="flex items-end gap-3">
              <div className="flex-1">
                <label className="block text-xs font-medium text-gray-500">Email</label>
                <input
                  type="email"
                  required
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                  placeholder="user@example.com"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500">Role</label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value)}
                  className="mt-1 rounded-md border border-gray-300 px-3 py-2 text-sm"
                >
                  <option value="member">member</option>
                  <option value="admin">admin</option>
                </select>
              </div>
              <button
                type="submit"
                className="flex items-center gap-1.5 rounded-md bg-highlight px-4 py-2 text-sm font-bold text-highlight-text hover:brightness-90"
              >
                <UserPlus className="h-4 w-4" />
                Invite
              </button>
            </form>

            {invites.length > 0 && (
              <div className="mt-4">
                <p className="text-xs font-medium text-gray-500">Pending Invites</p>
                <div className="mt-2 space-y-1">
                  {invites.map((inv) => (
                    <div
                      key={inv.id}
                      className="flex items-center justify-between rounded-md bg-gray-50 px-3 py-2 text-sm"
                    >
                      <span className="text-gray-700">{inv.email}</span>
                      <span className="text-xs text-gray-400">{inv.role}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Create new team */}
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <h3 className="mb-3 font-medium text-gray-900">Create New Team</h3>
          <form onSubmit={handleCreateTeam} className="flex items-end gap-3">
            <div className="flex-1">
              <input
                type="text"
                required
                value={newTeamName}
                onChange={(e) => setNewTeamName(e.target.value)}
                className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                placeholder="Team name"
              />
            </div>
            <button
              type="submit"
              className="rounded-md bg-highlight px-4 py-2 text-sm font-bold text-highlight-text hover:brightness-90"
            >
              Create
            </button>
          </form>
        </div>

        {/* All teams list */}
        <div className="rounded-lg border border-gray-200 bg-white">
          <div className="border-b border-gray-200 px-4 py-3">
            <h3 className="font-medium text-gray-900">All Teams</h3>
          </div>
          <div className="divide-y divide-gray-100">
            {teams.map((t) => (
              <div key={t.uuid} className="flex items-center justify-between px-4 py-3">
                <div>
                  <span className="text-sm font-medium text-gray-900">{t.name}</span>
                  <span className="ml-2 text-xs text-gray-400">{t.role}</span>
                </div>
                {t.uuid !== currentTeam?.uuid && (
                  <button
                    onClick={() => {
                      switchTeam(t.uuid)
                      refreshTeams()
                    }}
                    className="text-xs text-highlight hover:brightness-75"
                  >
                    Switch
                  </button>
                )}
                {t.uuid === currentTeam?.uuid && (
                  <span className="text-xs text-green-600">Current</span>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </PageLayout>
  )
}
