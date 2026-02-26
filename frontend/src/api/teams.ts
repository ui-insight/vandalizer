import { apiFetch } from './client'
import type { Team, TeamMember, TeamInvite } from '../types/user'

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
