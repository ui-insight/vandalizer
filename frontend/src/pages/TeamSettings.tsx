import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { UserPlus, Trash2, Pencil, Check, X, Copy, AlertTriangle, ArrowRightLeft, LogOut } from 'lucide-react'
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
  updateTeamName,
  transferOwnership,
  deleteTeam,
} from '../api/teams'

function getInviteExpiry(invite: TeamInvite): { label: string; expired: boolean } {
  if (!invite.created_at) return { label: '', expired: false }
  const created = new Date(invite.created_at)
  const expiresAt = new Date(created.getTime() + 30 * 24 * 60 * 60 * 1000)
  const now = new Date()
  if (now >= expiresAt) return { label: 'Expired', expired: true }
  const daysLeft = Math.ceil((expiresAt.getTime() - now.getTime()) / (24 * 60 * 60 * 1000))
  return { label: `Expires in ${daysLeft} day${daysLeft !== 1 ? 's' : ''}`, expired: false }
}

export function TeamSettings() {
  const { user } = useAuth()
  const { teams, currentTeam, switchTeam, refreshTeams } = useTeams()
  const navigate = useNavigate()
  const [members, setMembers] = useState<TeamMember[]>([])
  const [invites, setInvites] = useState<TeamInvite[]>([])
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState('member')
  const [newTeamName, setNewTeamName] = useState('')
  const [error, setError] = useState('')
  const [editingName, setEditingName] = useState(false)
  const [renameValue, setRenameValue] = useState('')
  const [transferTarget, setTransferTarget] = useState('')
  const [copiedToken, setCopiedToken] = useState<string | null>(null)

  const canEdit = currentTeam?.role === 'owner' || currentTeam?.role === 'admin'
  const isOwner = currentTeam?.role === 'owner'

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

  async function handleRename() {
    if (!currentTeam || !renameValue.trim()) return
    try {
      await updateTeamName(currentTeam.uuid, renameValue.trim())
      setEditingName(false)
      refreshTeams()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rename team')
    }
  }

  async function handleCreateTeam(e: FormEvent) {
    e.preventDefault()
    if (!newTeamName.trim()) return
    await createTeam(newTeamName.trim())
    setNewTeamName('')
    refreshTeams()
  }

  async function handleTransferOwnership() {
    if (!currentTeam || !transferTarget) return
    const confirmed = window.confirm(
      'Are you sure? You will be demoted to admin.',
    )
    if (!confirmed) return
    setError('')
    try {
      await transferOwnership(currentTeam.uuid, transferTarget)
      setTransferTarget('')
      await refreshTeams()
      refreshData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to transfer ownership')
    }
  }

  async function handleLeaveTeam() {
    if (!currentTeam || !user) return
    const confirmed = window.confirm(
      `Are you sure you want to leave "${currentTeam.name}"?`,
    )
    if (!confirmed) return
    setError('')
    try {
      await removeMember(currentTeam.uuid, user.user_id)
      await refreshTeams()
      navigate({ to: '/', search: { mode: undefined, tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: undefined } })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to leave team')
    }
  }

  async function handleDeleteTeam() {
    if (!currentTeam) return
    const confirmed = window.confirm(
      'Are you sure? This cannot be undone. All members will be removed.',
    )
    if (!confirmed) return
    setError('')
    try {
      await deleteTeam(currentTeam.uuid)
      await refreshTeams()
      navigate({ to: '/', search: { mode: undefined, tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: undefined } })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete team')
    }
  }

  function handleCopyInviteLink(token: string) {
    const link = `${window.location.origin}/invite?token=${token}`
    navigator.clipboard.writeText(link).then(() => {
      setCopiedToken(token)
      setTimeout(() => setCopiedToken(null), 2000)
    })
  }

  // Members eligible for ownership transfer (non-owner members)
  const transferCandidates = members.filter(
    (m) => m.user_id !== user?.user_id && m.role !== 'owner',
  )

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
              <div className="flex items-center gap-2">
                {editingName ? (
                  <>
                    <input
                      type="text"
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRename()
                        if (e.key === 'Escape') setEditingName(false)
                      }}
                      autoFocus
                      className="rounded-md border border-gray-300 px-2 py-1 text-sm font-medium focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                    />
                    <button
                      onClick={handleRename}
                      className="rounded p-1 text-green-600 hover:bg-green-50"
                    >
                      <Check className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => setEditingName(false)}
                      className="rounded p-1 text-gray-400 hover:bg-gray-100"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </>
                ) : (
                  <>
                    <h3 className="font-medium text-gray-900">{currentTeam.name}</h3>
                    {canEdit && (
                      <button
                        onClick={() => {
                          setRenameValue(currentTeam.name)
                          setEditingName(true)
                        }}
                        className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                        title="Rename team"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </>
                )}
              </div>
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
                  {invites.map((inv) => {
                    const expiry = getInviteExpiry(inv)
                    return (
                      <div
                        key={inv.id}
                        className="flex items-center justify-between rounded-md bg-gray-50 px-3 py-2 text-sm"
                      >
                        <div className="flex items-center gap-3">
                          <span className="text-gray-700">{inv.email}</span>
                          <span className="text-xs text-gray-400">{inv.role}</span>
                          {expiry.label && (
                            <span
                              className={`text-xs ${expiry.expired ? 'font-medium text-red-600' : 'text-gray-400'}`}
                            >
                              {expiry.label}
                            </span>
                          )}
                        </div>
                        <button
                          onClick={() => handleCopyInviteLink(inv.token)}
                          className="flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-500 hover:bg-gray-200 hover:text-gray-700"
                          title="Copy invite link"
                        >
                          <Copy className="h-3.5 w-3.5" />
                          {copiedToken === inv.token ? 'Copied!' : 'Copy Link'}
                        </button>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Transfer Ownership */}
        {isOwner && transferCandidates.length > 0 && (
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <h3 className="mb-1 font-medium text-gray-900 flex items-center gap-2">
              <ArrowRightLeft className="h-4 w-4" />
              Transfer Ownership
            </h3>
            <p className="mb-3 text-xs text-gray-500">
              Transfer team ownership to another member. You will be demoted to admin.
            </p>
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <label className="block text-xs font-medium text-gray-500">New Owner</label>
                <select
                  value={transferTarget}
                  onChange={(e) => setTransferTarget(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                >
                  <option value="">Select a member...</option>
                  {transferCandidates.map((m) => (
                    <option key={m.user_id} value={m.user_id}>
                      {m.name || m.email || m.user_id} ({m.role})
                    </option>
                  ))}
                </select>
              </div>
              <button
                onClick={handleTransferOwnership}
                disabled={!transferTarget}
                className="rounded-md bg-highlight px-4 py-2 text-sm font-bold text-highlight-text hover:brightness-90 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Transfer
              </button>
            </div>
          </div>
        )}

        {/* Leave Team (non-owners only) */}
        {currentTeam && !isOwner && (
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <h3 className="mb-1 font-medium text-gray-900 flex items-center gap-2">
              <LogOut className="h-4 w-4" />
              Leave Team
            </h3>
            <p className="mb-3 text-xs text-gray-500">
              Leave this team. You will lose access to shared documents and folders.
            </p>
            <button
              onClick={handleLeaveTeam}
              className="flex items-center gap-1.5 rounded-md border border-red-200 bg-red-50 px-4 py-2 text-sm font-bold text-red-600 hover:bg-red-100"
            >
              <LogOut className="h-4 w-4" />
              Leave Team
            </button>
          </div>
        )}

        {/* Delete Team */}
        {isOwner && (
          <div className="rounded-lg border border-red-200 bg-white p-4">
            <h3 className="mb-1 font-medium text-gray-900 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-red-500" />
              Delete Team
            </h3>
            <p className="mb-3 text-xs text-gray-500">
              Permanently delete this team and remove all members. This action cannot be undone.
            </p>
            <button
              onClick={handleDeleteTeam}
              className="flex items-center gap-1.5 rounded-md bg-red-600 px-4 py-2 text-sm font-bold text-white hover:bg-red-700"
            >
              <Trash2 className="h-4 w-4" />
              Delete Team
            </button>
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
                    onClick={() => switchTeam(t.uuid)}
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
