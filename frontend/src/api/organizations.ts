import { apiFetch } from './client'

export interface Organization {
  uuid: string
  name: string
  org_type: string
  parent_id: string | null
  metadata: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
  children?: Organization[]
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
