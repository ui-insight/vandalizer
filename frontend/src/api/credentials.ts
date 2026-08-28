import { apiFetch } from './client'
import type { Credential, CredentialType, CredentialTestResult } from '../types/credential'

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
  data: { name?: string; description?: string; payload?: Record<string, string>; type?: CredentialType },
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

/** Test an unsaved credential as typed (secrets travel in the request). */
export function testCredentialDraft(data: { type: CredentialType; payload: Record<string, string>; test_url?: string }) {
  return apiFetch<CredentialTestResult>('/api/credentials/test', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/** Test a saved credential with its stored secrets; unsaved edits merge over them. */
export function testCredential(id: string, data: { payload?: Record<string, string>; test_url?: string } = {}) {
  return apiFetch<CredentialTestResult>(`/api/credentials/${id}/test`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}
