import { apiFetch } from './client'
import type { Credential, CredentialType } from '../types/credential'

export function listCredentials() {
  return apiFetch<Credential[]>('/api/credentials')
}

export function getCredential(id: string) {
  return apiFetch<Credential>(`/api/credentials/${id}`)
}

export function createCredential(data: {
  name: string
  type: CredentialType
  description?: string
  payload: Record<string, string>
  team_id?: string
}) {
  return apiFetch<Credential>('/api/credentials', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateCredential(
  id: string,
  data: { name?: string; description?: string; payload?: Record<string, string> },
) {
  return apiFetch<Credential>(`/api/credentials/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteCredential(id: string) {
  return apiFetch<{ status: string; id: string }>(`/api/credentials/${id}`, {
    method: 'DELETE',
  })
}

export function invalidateCredentialCache(id: string) {
  return apiFetch<{ status: string; id: string }>(`/api/credentials/${id}/invalidate-cache`, {
    method: 'POST',
  })
}
