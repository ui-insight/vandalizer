import { apiFetch } from './client'
import type { Team, TeamMember, TeamInvite, TeamJoinLink } from '../types/user'

export function listTeams() {
  return apiFetch<Team[]>('/api/teams/')
}

export function createTeam(name: string) {
  return apiFetch<{ id: string; uuid: string; name: string }>('/api/teams/create', {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}

export function updateTeamName(team_id: string, name: string) {
  return apiFetch<{ status: string; name: string }>('/api/teams/update_name', {
    method: 'PATCH',
    body: JSON.stringify({ team_id, name }),
  })
}

export function switchTeam(teamUuid: string) {
  return apiFetch<{ uuid: string; name: string }>(`/api/teams/switch/${teamUuid}`, {
    method: 'POST',
  })
}

export function getTeamMembers(teamUuid: string) {
  return apiFetch<TeamMember[]>(`/api/teams/${teamUuid}/members`)
}

export function getTeamInvites(teamUuid: string) {
  return apiFetch<TeamInvite[]>(`/api/teams/${teamUuid}/invites`)
}

export function inviteMember(team_id: string, email: string, role: string = 'member') {
  return apiFetch<{ token: string; email: string }>('/api/teams/invite', {
    method: 'POST',
    body: JSON.stringify({ team_id, email, role }),
  })
}

export function acceptInvite(token: string) {
  return apiFetch<{ uuid: string; name: string }>(`/api/teams/invite/accept/${token}`, {
    method: 'POST',
  })
}

export interface InviteInfo {
  email: string
  role: string
  team_name: string
  team_uuid: string | null
  inviter_name: string | null
  expired: boolean
}

export async function getInviteInfo(token: string): Promise<InviteInfo> {
  const res = await fetch(`/api/teams/invite/info/${encodeURIComponent(token)}`)
  if (!res.ok) {
    throw new Error('Invalid or expired invite link.')
  }
  return res.json()
}

export function changeMemberRole(team_id: string, user_id: string, role: string) {
  return apiFetch<{ ok: boolean }>('/api/teams/member/role', {
    method: 'POST',
    body: JSON.stringify({ team_id, user_id, role }),
  })
}

export function removeMember(team_id: string, user_id: string) {
  return apiFetch<{ ok: boolean }>('/api/teams/member/remove', {
    method: 'POST',
    body: JSON.stringify({ team_id, user_id }),
  })
}

export function transferOwnership(teamUuid: string, newOwnerUserId: string) {
  return apiFetch<{ ok: boolean }>('/api/teams/transfer-ownership', {
    method: 'POST',
    body: JSON.stringify({ team_uuid: teamUuid, new_owner_user_id: newOwnerUserId }),
  })
}

export function deleteTeam(teamUuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/teams/${teamUuid}`, {
    method: 'DELETE',
  })
}

// ---------------------------------------------------------------------------
// Public join links
// ---------------------------------------------------------------------------

export interface CreateJoinLinkParams {
  role?: string
  expires_in_hours?: number
  max_uses?: number | null
}

export function createJoinLink(teamUuid: string, params: CreateJoinLinkParams = {}) {
  return apiFetch<TeamJoinLink>(`/api/teams/${teamUuid}/join-link`, {
    method: 'POST',
    body: JSON.stringify({
      role: params.role ?? 'member',
      expires_in_hours: params.expires_in_hours ?? 48,
      max_uses: params.max_uses ?? null,
    }),
  })
}

export function getJoinLinks(teamUuid: string) {
  return apiFetch<TeamJoinLink[]>(`/api/teams/${teamUuid}/join-links`)
}

export function revokeJoinLink(token: string) {
  return apiFetch<{ ok: boolean }>(
    `/api/teams/join-link/${encodeURIComponent(token)}`,
    { method: 'DELETE' },
  )
}

export interface JoinLinkInfo {
  role: string
  team_name: string
  team_uuid: string | null
  inviter_name: string | null
  expires_at: string | null
  status: null | 'revoked' | 'expired' | 'exhausted'
}

export async function getJoinLinkInfo(token: string): Promise<JoinLinkInfo> {
  const res = await fetch(`/api/teams/join-link/info/${encodeURIComponent(token)}`)
  if (!res.ok) {
    throw new Error('Invalid join link.')
  }
  return res.json()
}

export function acceptJoinLink(token: string) {
  return apiFetch<{ uuid: string; name: string }>(
    `/api/teams/join-link/accept/${encodeURIComponent(token)}`,
    { method: 'POST' },
  )
}
