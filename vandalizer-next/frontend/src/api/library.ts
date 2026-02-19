import { apiFetch } from './client'
import type { Library, LibraryItem, LibraryFolder, LibraryItemKind, VerificationRequest } from '../types/library'

// Library CRUD

export function listLibraries(teamId?: string) {
  const params = teamId ? `?team_id=${encodeURIComponent(teamId)}` : ''
  return apiFetch<Library[]>(`/api/library${params}`)
}

export function getLibrary(id: string) {
  return apiFetch<Library>(`/api/library/${id}`)
}

export function updateLibrary(id: string, data: { title?: string; description?: string }) {
  return apiFetch<Library>(`/api/library/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export function deleteLibrary(id: string) {
  return apiFetch<{ ok: boolean }>(`/api/library/${id}`, { method: 'DELETE' })
}

// Items

export function addItem(libraryId: string, data: { item_id: string; kind: string; note?: string; tags?: string[]; folder?: string }) {
  return apiFetch<LibraryItem>(`/api/library/${libraryId}/items`, { method: 'POST', body: JSON.stringify(data) })
}

export function listItems(libraryId: string, params?: { kind?: string; folder?: string; search?: string }) {
  const searchParams = new URLSearchParams()
  if (params?.kind) searchParams.set('kind', params.kind)
  if (params?.folder) searchParams.set('folder', params.folder)
  if (params?.search) searchParams.set('search', params.search)
  const qs = searchParams.toString()
  return apiFetch<LibraryItem[]>(`/api/library/${libraryId}/items${qs ? `?${qs}` : ''}`)
}

export function updateItem(itemId: string, data: { note?: string; tags?: string[]; pinned?: boolean; favorited?: boolean }) {
  return apiFetch<LibraryItem>(`/api/library/items/${itemId}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export function removeItem(libraryId: string, itemId: string) {
  return apiFetch<{ ok: boolean }>(`/api/library/${libraryId}/items/${itemId}`, { method: 'DELETE' })
}

// Clone / Share

export function cloneToPersonal(itemId: string) {
  return apiFetch<LibraryItem>('/api/library/clone', { method: 'POST', body: JSON.stringify({ item_id: itemId }) })
}

export function shareToTeam(itemId: string, teamId: string) {
  return apiFetch<LibraryItem>('/api/library/share', { method: 'POST', body: JSON.stringify({ item_id: itemId, team_id: teamId }) })
}

// Folders

export function createFolder(data: { name: string; parent_id?: string; scope: string; team_id?: string }) {
  return apiFetch<LibraryFolder>('/api/library/folders', { method: 'POST', body: JSON.stringify(data) })
}

export function renameFolder(uuid: string, name: string) {
  return apiFetch<LibraryFolder>(`/api/library/folders/${uuid}`, { method: 'PATCH', body: JSON.stringify({ name }) })
}

export function deleteFolder(uuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/library/folders/${uuid}`, { method: 'DELETE' })
}

export function moveItems(itemIds: string[], folderUuid: string | null) {
  return apiFetch<{ ok: boolean }>('/api/library/folders/move-items', {
    method: 'POST',
    body: JSON.stringify({ item_ids: itemIds, folder_uuid: folderUuid }),
  })
}

// Search

export function searchLibraries(query: string, kind?: LibraryItemKind, teamId?: string) {
  return apiFetch<LibraryItem[]>('/api/library/search', {
    method: 'POST',
    body: JSON.stringify({ query, kind, team_id: teamId }),
  })
}

// Verification

export function submitForVerification(data: {
  item_kind: string
  item_id: string
  submitter_name?: string
  summary?: string
  description?: string
  category?: string
}) {
  return apiFetch<VerificationRequest>('/api/verification/submit', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function listVerificationQueue(status?: string, limit = 50) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  params.set('limit', String(limit))
  return apiFetch<{ requests: VerificationRequest[] }>(`/api/verification/queue?${params}`)
}

export function myVerificationRequests(limit = 50) {
  return apiFetch<{ requests: VerificationRequest[] }>(`/api/verification/mine?limit=${limit}`)
}

export function updateVerificationStatus(requestUuid: string, status: string, reviewerNotes?: string) {
  return apiFetch<VerificationRequest>(`/api/verification/${requestUuid}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status, reviewer_notes: reviewerNotes }),
  })
}
