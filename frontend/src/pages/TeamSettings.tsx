import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { UserPlus, Trash2, Pencil, Check, X, Copy, AlertTriangle, ArrowRightLeft, LogOut, Link2, Link2Off } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useTeams } from '../hooks/useTeams'
import { useAuth } from '../hooks/useAuth'
import { useConfirm } from '../components/shared/useConfirm'
import { nameWithoutEmail } from '../lib/displayName'
import type { TeamMember, TeamInvite, TeamJoinLink } from '../types/user'
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
  createJoinLink,
  getJoinLinks,
  revokeJoinLink,
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

function getJoinLinkExpiry(link: TeamJoinLink): { label: string; expired: boolean } {
  if (!link.expires_at) return { label: '', expired: false }
  const expiresAt = new Date(link.expires_at)
  const now = new Date()
  if (now >= expiresAt) return { label: 'Expired', expired: true }
  const msLeft = expiresAt.getTime() - now.getTime()
  const hoursLeft = Math.ceil(msLeft / (60 * 60 * 1000))
  if (hoursLeft <= 48) {
    return { label: `Expires in ${hoursLeft}h`, expired: false }
  }
  const daysLeft = Math.ceil(hoursLeft / 24)
  return { label: `Expires in ${daysLeft}d`, expired: false }
}

export function TeamSettings() {
  const { currentTeam } = useTeams()
  return <TeamSettingsContent key={currentTeam?.uuid ?? 'no-team'} />
}

function TeamSettingsContent() {
  const { user } = useAuth()
  const { teams, currentTeam, switchTeam, refreshTeams, error: teamsError } = useTeams()
  const navigate = useNavigate()
  const confirm = useConfirm()
  const [members, setMembers] = useState<TeamMember[]>([])
  const [invites, setInvites] = useState<TeamInvite[]>([])
  const [joinLinks, setJoinLinks] = useState<TeamJoinLink[]>([])
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState('member')
  const [newTeamName, setNewTeamName] = useState('')
  const [error, setError] = useState('')
  const [editingName, setEditingName] = useState(false)
  const [renameValue, setRenameValue] = useState('')
  const [transferTarget, setTransferTarget] = useState('')
  const [copiedToken, setCopiedToken] = useState<string | null>(null)
  const [joinLinkRole, setJoinLinkRole] = useState('member')
  const [joinLinkExpiry, setJoinLinkExpiry] = useState(48)
  const [creatingJoinLink, setCreatingJoinLink] = useState(false)
  const [pendingAction, setPendingAction] = useState<string | null>(null)
  const pendingActionRef = useRef(false)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState('')
  function beginAction(label: string) {
    if (pendingActionRef.current) return false
    pendingActionRef.current = true
    setPendingAction(label)
    setError('')
    return true
  }
  function endAction() { pendingActionRef.current = false; setPendingAction(null) }

  const canEdit = currentTeam?.role === 'owner' || currentTeam?.role === 'admin'
  const isOwner = currentTeam?.role === 'owner'

  const refreshData = useCallback(async () => {
    if (!currentTeam) return
    setLoading(true)
    setLoadError('')
    try {
      const [m, i, l] = await Promise.all([
        getTeamMembers(currentTeam.uuid),
        // Members can see their team roster, but pending invitations and join
        // links are admin controls. Don't generate an avoidable 403 for them.
        canEdit ? getTeamInvites(currentTeam.uuid) : Promise.resolve([]),
        canEdit ? getJoinLinks(currentTeam.uuid) : Promise.resolve([]),
      ])
      setMembers(m)
      setInvites(i)
      setJoinLinks(l)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load team details')
    } finally { setLoading(false) }
  }, [currentTeam, canEdit])

  useEffect(() => {
    refreshData()
  }, [refreshData])

  async function handleInvite(e: FormEvent) {
    e.preventDefault()
    if (!currentTeam || !inviteEmail.trim()) return
    setError('')
    if (!beginAction('Sending invitation…')) return
    try {
      await inviteMember(currentTeam.uuid, inviteEmail.trim(), inviteRole)
      setInviteEmail('')
      refreshData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to invite')
    } finally { endAction() }
  }

  async function handleRoleChange(userId: string, role: string) {
    if (!currentTeam) return
    if (!beginAction('Saving role…')) return
    try {
      await changeMemberRole(currentTeam.uuid, userId, role)
      refreshData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to change role')
    } finally { endAction() }
  }

  async function handleRemove(userId: string) {
    if (!currentTeam) return
    const member = members.find(m => m.user_id === userId)
    const ok = await confirm({
      title: 'Remove member?',
      message: (
        <>
          Are you sure you want to remove <strong>{member?.name || member?.email || 'this member'}</strong> from <strong>{currentTeam.name}</strong>? They will lose access to the team's content.
        </>
      ),
      confirmLabel: 'Remove',
      destructive: true,
    })
    if (!ok) return
    if (!beginAction('Removing member…')) return
    try {
      await removeMember(currentTeam.uuid, userId)
      refreshData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove member')
    } finally { endAction() }
  }

  async function handleRename() {
    if (!currentTeam || !renameValue.trim()) return
    if (!beginAction('Saving team name…')) return
    try {
      await updateTeamName(currentTeam.uuid, renameValue.trim())
      setEditingName(false)
      refreshTeams()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rename team')
    } finally { endAction() }
  }

  async function handleCreateTeam(e: FormEvent) {
    e.preventDefault()
    if (!newTeamName.trim() || !beginAction('Creating team…')) return
    try {
      await createTeam(newTeamName.trim())
      setNewTeamName('')
      await refreshTeams()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not create team. Your name is kept; try again.')
    } finally { endAction() }
  }

  async function handleTransferOwnership() {
    if (!currentTeam || !transferTarget) return
    const target = members.find(m => m.user_id === transferTarget)
    const confirmed = await confirm({
      title: 'Transfer ownership?',
      message: (
        <>
          Transfer ownership of <strong>{currentTeam.name}</strong> to <strong>{target?.name || target?.email || 'this member'}</strong>? You will be demoted to admin and lose owner permissions.
        </>
      ),
      confirmLabel: 'Transfer',
      destructive: true,
    })
    if (!confirmed) return
    setError('')
    if (!beginAction('Transferring ownership…')) return
    try {
      await transferOwnership(currentTeam.uuid, transferTarget)
      setTransferTarget('')
      await refreshTeams()
      refreshData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to transfer ownership')
    } finally { endAction() }
  }

  async function handleLeaveTeam() {
    if (!currentTeam || !user) return
    const confirmed = await confirm({
      title: 'Leave team?',
      message: (
        <>
          Are you sure you want to leave <strong>{currentTeam.name}</strong>? You will lose access to the team's content.
        </>
      ),
      confirmLabel: 'Leave team',
      destructive: true,
    })
    if (!confirmed) return
    setError('')
    if (!beginAction('Leaving team…')) return
    try {
      await removeMember(currentTeam.uuid, user.user_id)
      await refreshTeams()
      navigate({ to: '/', search: { mode: undefined, tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: undefined, project: undefined, workflow_share_token: undefined } })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to leave team')
    } finally { endAction() }
  }

  async function handleDeleteTeam() {
    if (!currentTeam) return
    const confirmed = await confirm({
      title: 'Delete team?',
      message: (
        <>
          Are you sure you want to delete <strong>{currentTeam.name}</strong>? All members will be removed and all team content will be lost. This cannot be undone.
        </>
      ),
      confirmLabel: 'Delete team',
      destructive: true,
    })
    if (!confirmed) return
    setError('')
    if (!beginAction('Deleting team…')) return
    try {
      await deleteTeam(currentTeam.uuid)
      await refreshTeams()
      navigate({ to: '/', search: { mode: undefined, tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: undefined, project: undefined, workflow_share_token: undefined } })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete team')
    } finally { endAction() }
  }

  function handleCopyInviteLink(token: string) {
    const link = `${window.location.origin}/invite?token=${token}`
    navigator.clipboard.writeText(link).then(() => {
      setCopiedToken(token)
      setTimeout(() => setCopiedToken(null), 2000)
    }).catch(() => setError('Could not copy the link. Try again or allow clipboard access.'))
  }

  function handleCopyJoinLink(token: string) {
    const link = `${window.location.origin}/join?token=${token}`
    navigator.clipboard.writeText(link).then(() => {
      setCopiedToken(token)
      setTimeout(() => setCopiedToken(null), 2000)
    }).catch(() => setError('Could not copy the link. Try again or allow clipboard access.'))
  }

  async function handleCreateJoinLink() {
    if (!currentTeam || !beginAction('Creating join link…')) return
    setError('')
    setCreatingJoinLink(true)
    try {
      await createJoinLink(currentTeam.uuid, {
        role: joinLinkRole,
        expires_in_hours: joinLinkExpiry,
      })
      refreshData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create join link')
    } finally {
      setCreatingJoinLink(false)
      endAction()
    }
  }

  async function handleRevokeJoinLink(token: string) {
    const confirmed = await confirm({
      title: 'Revoke join link?',
      message: 'Anyone with this link will no longer be able to use it to join the team.',
      confirmLabel: 'Revoke',
      destructive: true,
    })
    if (!confirmed) return
    setError('')
    if (!beginAction('Revoking join link…')) return
    try {
      await revokeJoinLink(token)
      refreshData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to revoke join link')
    } finally { endAction() }
  }

  // Members eligible for ownership transfer (non-owner members)
  const transferCandidates = members.filter(
    (m) => m.user_id !== user?.user_id && m.role !== 'owner',
  )

  return (
    <PageLayout>
      <fieldset disabled={!!pendingAction} aria-label="Team settings" className="mx-auto min-w-0 max-w-3xl space-y-6 border-0 p-0">
        <h1 className="text-xl font-semibold text-gray-900">Teams</h1>

        {teamsError && <div role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-800">{teamsError} <button type="button" className="underline" onClick={() => void refreshTeams()}>Retry teams</button></div>}
        {pendingAction && <p role="status" className="text-sm text-gray-700">{pendingAction}</p>}
        {loading && <p role="status" className="text-sm text-gray-700">Loading team details…</p>}
        {loadError && <div role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-800">{loadError} <button type="button" className="underline" onClick={() => void refreshData()}>Retry team details</button></div>}
        {error && (
          <div role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
        )}

        {/* Current team members */}
        {currentTeam && (
          <div className="rounded-lg border border-gray-200 bg-white">
            <div className="border-b border-gray-200 px-4 py-3">
              <div className="flex items-center gap-2">
                {editingName ? (
                  <>
                    <input
                      aria-label="Team name"
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
                      type="button"
                      aria-label="Save team name"
                      onClick={handleRename}
                      className="rounded p-1 text-green-700 hover:bg-green-50"
                    >
                      <Check className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      aria-label="Cancel rename"
                      onClick={() => setEditingName(false)}
                      className="rounded p-1 text-gray-600 hover:bg-gray-100"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </>
                ) : (
                  <>
                    <h3 className="font-medium text-gray-900">{currentTeam.name}</h3>
                    {canEdit && (
                      <button
                        type="button"
                        aria-label="Rename team"
                        onClick={() => {
                          setRenameValue(currentTeam.name)
                          setEditingName(true)
                        }}
                        className="rounded p-1 text-gray-600 hover:bg-gray-100 hover:text-gray-600"
                        title="Rename team"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </>
                )}
              </div>
              <p className="text-xs text-gray-500">Your role in this team: {currentTeam.role}</p>
              <p className="mt-1 text-xs text-gray-600">Team roles control this team’s members and shared work. They are separate from account-level access.</p>
            </div>
            <table className="team-members-table w-full">
              <thead>
                <tr className="border-b border-gray-100 text-left">
                  <th scope="col" className="px-4 py-2 text-xs font-medium uppercase text-gray-500">Member</th>
                  <th scope="col" className="px-4 py-2 text-xs font-medium uppercase text-gray-500">Role</th>
                  {canEdit && <th className="w-20 px-4 py-2" />}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {members.map((m) => (
                  <tr key={m.user_id}>
                    <td className="px-4 py-3">
                      <div className="text-sm font-medium text-gray-900">
                        {nameWithoutEmail(m.name, m.email) || m.user_id}
                      </div>
                      {m.email && <div className="text-xs text-gray-500">{m.email}</div>}
                    </td>
                    <td className="px-4 py-3">
                      {canEdit && m.user_id !== user?.user_id && m.role !== 'owner' ? (
                        <select
                          aria-label={`Role for ${nameWithoutEmail(m.name, m.email) || m.email || m.user_id}`}
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
                            type="button"
                            aria-label={`Remove ${nameWithoutEmail(m.name, m.email) || m.email || m.user_id}`}
                            onClick={() => handleRemove(m.user_id)}
                            className="rounded p-1 text-gray-600 hover:bg-red-50 hover:text-red-700"
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
            <form onSubmit={handleInvite} className="flex flex-wrap items-end gap-3">
              <div className="min-w-0 flex-[1_1_200px]">
                <label htmlFor="invite-email" className="block text-xs font-medium text-gray-500">Email</label>
                <input
                  id="invite-email"
                  type="email"
                  required
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
                  placeholder="user@example.com"
                />
              </div>
              <div>
                <label htmlFor="invite-role" className="block text-xs font-medium text-gray-500">Role</label>
                <select
                  id="invite-role"
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
                          <span className="text-xs text-gray-500">{inv.role}</span>
                          {expiry.label && (
                            <span
                              className={`text-xs ${expiry.expired ? 'font-medium text-red-700' : 'text-gray-600'}`}
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

        {/* Share Join Link */}
        {canEdit && (
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <h3 className="mb-1 font-medium text-gray-900 flex items-center gap-2">
              <Link2 className="h-4 w-4" />
              Share Join Link
            </h3>
            <p className="mb-3 text-xs text-gray-500">
              Create a public link anyone can use to join this team. Links
              expire after a set time and can be revoked anytime.
            </p>
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <label htmlFor="joinlink-role" className="block text-xs font-medium text-gray-500">Role</label>
                <select
                  id="joinlink-role"
                  value={joinLinkRole}
                  onChange={(e) => setJoinLinkRole(e.target.value)}
                  className="mt-1 rounded-md border border-gray-300 px-3 py-2 text-sm"
                >
                  <option value="member">member</option>
                  <option value="admin">admin</option>
                </select>
              </div>
              <div>
                <label htmlFor="joinlink-expiry" className="block text-xs font-medium text-gray-500">Expires in</label>
                <select
                  id="joinlink-expiry"
                  value={joinLinkExpiry}
                  onChange={(e) => setJoinLinkExpiry(Number(e.target.value))}
                  className="mt-1 rounded-md border border-gray-300 px-3 py-2 text-sm"
                >
                  <option value={1}>1 hour</option>
                  <option value={24}>24 hours</option>
                  <option value={48}>48 hours</option>
                  <option value={168}>7 days</option>
                  <option value={720}>30 days</option>
                </select>
              </div>
              <button
                onClick={handleCreateJoinLink}
                disabled={creatingJoinLink}
                className="flex items-center gap-1.5 rounded-md bg-highlight px-4 py-2 text-sm font-bold text-highlight-text hover:brightness-90 disabled:opacity-50"
              >
                <Link2 className="h-4 w-4" />
                {creatingJoinLink ? 'Creating...' : 'Create Link'}
              </button>
            </div>

            {joinLinks.length > 0 && (
              <div className="mt-4">
                <p className="text-xs font-medium text-gray-500">Active Join Links</p>
                <div className="mt-2 space-y-1">
                  {joinLinks.map((link) => {
                    const expiry = getJoinLinkExpiry(link)
                    return (
                      <div
                        key={link.id}
                        className="flex items-center justify-between rounded-md bg-gray-50 px-3 py-2 text-sm"
                      >
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-gray-500">{link.role}</span>
                          <span className="text-xs text-gray-500">
                            {link.use_count} {link.use_count === 1 ? 'use' : 'uses'}
                          </span>
                          {expiry.label && (
                            <span
                              className={`text-xs ${expiry.expired ? 'font-medium text-red-700' : 'text-gray-600'}`}
                            >
                              {expiry.label}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleCopyJoinLink(link.token)}
                            className="flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-500 hover:bg-gray-200 hover:text-gray-700"
                            title="Copy join link"
                          >
                            <Copy className="h-3.5 w-3.5" />
                            {copiedToken === link.token ? 'Copied!' : 'Copy'}
                          </button>
                          <button
                            onClick={() => handleRevokeJoinLink(link.token)}
                            className="flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-500 hover:bg-red-50 hover:text-red-700"
                            title="Revoke link"
                          >
                            <Link2Off className="h-3.5 w-3.5" />
                            Revoke
                          </button>
                        </div>
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
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-0 flex-[1_1_200px]">
                <label htmlFor="transfer-target" className="block text-xs font-medium text-gray-500">New Owner</label>
                <select
                  id="transfer-target"
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
              className="flex items-center gap-1.5 rounded-md border border-red-200 bg-red-50 px-4 py-2 text-sm font-bold text-red-700 hover:bg-red-100"
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
          <form onSubmit={handleCreateTeam} className="flex flex-wrap items-end gap-3">
            <div className="min-w-0 flex-[1_1_200px]">
              <input
                aria-label="New team name"
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
                  <span className="ml-2 text-xs text-gray-500">{t.role}</span>
                </div>
                {t.uuid !== currentTeam?.uuid && (
                  <button
                    onClick={() => void switchTeam(t.uuid).catch(reason => setError(reason instanceof Error ? reason.message : 'Could not switch teams. Try again.'))}
                    className="text-xs text-highlight-on-light hover:brightness-75"
                  >
                    Switch
                  </button>
                )}
                {t.uuid === currentTeam?.uuid && (
                  <span className="text-xs text-green-700">Current</span>
                )}
              </div>
            ))}
          </div>
        </div>
      </fieldset>
    </PageLayout>
  )
}
