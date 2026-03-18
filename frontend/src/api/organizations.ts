import { apiFetch } from './client'

export interface Organization {
  uuid: string
  name: string
  org_type: string
  parent_id: string | null
  metadata: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
  user_count?: number
  team_count?: number
  children?: Organization[]
}

export interface OrgMember {
  user_id: string
  name: string | null
  email: string | null
}

export interface OrgTeam {
  uuid: string
  name: string
  owner_user_id: string
}

export function getOrgTree(): Promise<{ tree: Organization[] }> {
  return apiFetch('/api/organizations/tree')
}

export function listOrganizations(params?: {
  org_type?: string
  parent_id?: string
}): Promise<{ organizations: Organization[] }> {
  const qs = new URLSearchParams()
  if (params?.org_type) qs.set('org_type', params.org_type)
  if (params?.parent_id) qs.set('parent_id', params.parent_id)
  const query = qs.toString()
  return apiFetch(`/api/organizations/${query ? `?${query}` : ''}`)
}

export function getOrganization(uuid: string): Promise<Organization> {
  return apiFetch(`/api/organizations/${uuid}`)
}

export function createOrganization(data: {
  name: string
  org_type: string
  parent_id?: string
  metadata?: Record<string, unknown>
}): Promise<Organization> {
  return apiFetch('/api/organizations/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function updateOrganization(
  uuid: string,
  data: { name?: string; metadata?: Record<string, unknown> },
): Promise<Organization> {
  return apiFetch(`/api/organizations/${uuid}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function deleteOrganization(uuid: string): Promise<{ detail: string }> {
  return apiFetch(`/api/organizations/${uuid}`, { method: 'DELETE' })
}

export function assignUserToOrg(
  orgUuid: string,
  userId: string,
): Promise<{ detail: string }> {
  return apiFetch(`/api/organizations/${orgUuid}/assign-user/${userId}`, {
    method: 'POST',
  })
}

export function assignTeamToOrg(
  orgUuid: string,
  teamUuid: string,
): Promise<{ detail: string }> {
  return apiFetch(`/api/organizations/${orgUuid}/assign-team/${teamUuid}`, {
    method: 'POST',
  })
}

export function getMyOrg(): Promise<{
  organization: Organization | null
  ancestry: Organization[]
}> {
  return apiFetch('/api/organizations/me')
}

export function getOrgMembers(orgUuid: string): Promise<{
  users: OrgMember[]
  teams: OrgTeam[]
}> {
  return apiFetch(`/api/organizations/${orgUuid}/members`)
}

export function listOrganizationsFlat(): Promise<{ organizations: Organization[] }> {
  return apiFetch('/api/organizations/flat')
}

export function moveOrganization(uuid: string, newParentId: string | null): Promise<Organization> {
  return apiFetch(`/api/organizations/${uuid}/move`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_parent_id: newParentId }),
  })
}

export function updateOrgType(uuid: string, orgType: string): Promise<Organization> {
  return apiFetch(`/api/organizations/${uuid}/type`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ org_type: orgType }),
  })
}

export function importOrganizations(
  nodes: { name: string; parent_name?: string; org_type: string }[],
): Promise<{ created: Organization[]; count: number }> {
  return apiFetch('/api/organizations/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nodes }),
  })
}

export function unassignUserFromOrg(orgUuid: string, userId: string): Promise<{ detail: string }> {
  return apiFetch(`/api/organizations/${orgUuid}/unassign-user/${userId}`, { method: 'POST' })
}

export function unassignTeamFromOrg(orgUuid: string, teamUuid: string): Promise<{ detail: string }> {
  return apiFetch(`/api/organizations/${orgUuid}/unassign-team/${teamUuid}`, { method: 'POST' })
}

export function searchUsers(query: string): Promise<{ users: OrgMember[] }> {
  return apiFetch(`/api/verification/examiners/search?q=${encodeURIComponent(query)}`)
}
