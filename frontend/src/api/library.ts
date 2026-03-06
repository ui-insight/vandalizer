import { apiFetch } from './client'
import type {
  Library, LibraryItem, LibraryFolder, LibraryItemKind,
  VerificationRequest, VerifiedCatalogItem, VerifiedItemMetadata,
  VerifiedCollection, ExaminerUser, Group, GroupMember,
} from '../types/library'

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

export function touchItem(itemId: string) {
  return apiFetch<{ ok: boolean }>(`/api/library/items/${itemId}/touch`, { method: 'POST' })
}

// Clone / Share

export function cloneToPersonal(itemId: string) {
  return apiFetch<LibraryItem>('/api/library/clone', { method: 'POST', body: JSON.stringify({ item_id: itemId }) })
}

export function shareToTeam(itemId: string, teamId: string) {
  return apiFetch<LibraryItem>('/api/library/share', { method: 'POST', body: JSON.stringify({ item_id: itemId, team_id: teamId }) })
}

// Folders

export function listFolders(scope: string, teamId?: string) {
  const params = new URLSearchParams({ scope })
  if (teamId) params.set('team_id', teamId)
  return apiFetch<LibraryFolder[]>(`/api/library/folders?${params}`)
}

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

// Catalog Export / Import

export function exportCatalogUrl() {
  return '/api/verification/catalog/export'
}

export interface CatalogPreviewItem {
  index: number
  item_kind: string
  name: string
  description: string
  quality_tier: string | null
  quality_grade: string | null
}

export async function previewCatalogImport(file: File): Promise<CatalogPreviewItem[]> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch('/api/verification/catalog/preview-import', {
    method: 'POST',
    credentials: 'include',
    body: form,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Preview failed' }))
    throw new Error(body.detail || 'Preview failed')
  }
  const data = await res.json()
  return data.items
}

export async function importCatalogItems(
  file: File,
  selectedIndices: number[],
  space: string,
): Promise<{ imported: { kind: string; id?: string; uuid?: string; name: string }[] }> {
  const form = new FormData()
  form.append('file', file)
  form.append('selected_indices', JSON.stringify(selectedIndices))
  form.append('space', space)
  const res = await fetch('/api/verification/catalog/import', {
    method: 'POST',
    credentials: 'include',
    body: form,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Import failed' }))
    throw new Error(body.detail || 'Import failed')
  }
  return res.json()
}

// Verification - Queue

export function submitForVerification(data: {
  item_kind: string
  item_id: string
  submitter_name?: string
  summary?: string
  description?: string
  category?: string
  submitter_org?: string
  run_instructions?: string
  evaluation_notes?: string
  known_limitations?: string
  example_inputs?: string[]
  expected_outputs?: string[]
  dependencies?: string[]
  intended_use_tags?: string[]
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

export function updateVerificationStatus(
  requestUuid: string,
  status: string,
  reviewerNotes?: string,
  groupIds?: string[],
  collectionIds?: string[],
) {
  return apiFetch<VerificationRequest>(`/api/verification/${requestUuid}/status`, {
    method: 'PATCH',
    body: JSON.stringify({
      status,
      reviewer_notes: reviewerNotes,
      group_ids: groupIds,
      collection_ids: collectionIds,
    }),
  })
}

// Verification - Verified Catalog

export function listVerifiedItems(kind?: string, search?: string) {
  const params = new URLSearchParams()
  if (kind) params.set('kind', kind)
  if (search) params.set('search', search)
  const qs = params.toString()
  return apiFetch<{ items: VerifiedCatalogItem[] }>(`/api/verification/verified${qs ? `?${qs}` : ''}`)
}

export function getItemMetadata(itemKind: string, itemId: string) {
  return apiFetch<VerifiedItemMetadata>(`/api/verification/verified/${itemKind}/${itemId}/metadata`)
}

export function updateItemMetadata(itemKind: string, itemId: string, data: { display_name?: string; description?: string; markdown?: string; group_ids?: string[] }) {
  return apiFetch<VerifiedItemMetadata>(`/api/verification/verified/${itemKind}/${itemId}/metadata`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function unverifyItem(itemKind: string, itemId: string) {
  return apiFetch<{ ok: boolean }>(`/api/verification/verified/${itemKind}/${itemId}/unverify`, {
    method: 'POST',
  })
}

// Verification - Collections

export function listCollections() {
  return apiFetch<{ collections: VerifiedCollection[] }>('/api/verification/collections')
}

export function createCollection(data: { title: string; description?: string }) {
  return apiFetch<VerifiedCollection>('/api/verification/collections', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateCollection(id: string, data: { title?: string; description?: string }) {
  return apiFetch<VerifiedCollection>(`/api/verification/collections/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteCollection(id: string) {
  return apiFetch<{ ok: boolean }>(`/api/verification/collections/${id}`, { method: 'DELETE' })
}

export function addToCollection(collectionId: string, itemId: string) {
  return apiFetch<VerifiedCollection>(`/api/verification/collections/${collectionId}/items`, {
    method: 'POST',
    body: JSON.stringify({ item_id: itemId }),
  })
}

export function removeFromCollection(collectionId: string, itemId: string) {
  return apiFetch<VerifiedCollection>(`/api/verification/collections/${collectionId}/items/${itemId}`, {
    method: 'DELETE',
  })
}

// Verification - Examiners

export function listExaminers() {
  return apiFetch<{ examiners: ExaminerUser[] }>('/api/verification/examiners')
}

export function setExaminer(userId: string, isExaminer: boolean) {
  return apiFetch<ExaminerUser>('/api/verification/examiners', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, is_examiner: isExaminer }),
  })
}

export function searchUsersForExaminer(query: string) {
  return apiFetch<{ users: ExaminerUser[] }>(`/api/verification/examiners/search?q=${encodeURIComponent(query)}`)
}

// Groups

export function listGroups() {
  return apiFetch<{ groups: Group[] }>('/api/verification/groups')
}

export function createGroup(data: { name: string; description?: string }) {
  return apiFetch<Group>('/api/verification/groups', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateGroup(uuid: string, data: { name?: string; description?: string }) {
  return apiFetch<Group>(`/api/verification/groups/${uuid}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteGroup(uuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/verification/groups/${uuid}`, { method: 'DELETE' })
}

export function listGroupMembers(uuid: string) {
  return apiFetch<{ members: GroupMember[] }>(`/api/verification/groups/${uuid}/members`)
}

export function addGroupMember(groupUuid: string, userId: string) {
  return apiFetch<{ ok: boolean }>(`/api/verification/groups/${groupUuid}/members`, {
    method: 'POST',
    body: JSON.stringify({ user_id: userId }),
  })
}

export function removeGroupMember(groupUuid: string, userId: string) {
  return apiFetch<{ ok: boolean }>(`/api/verification/groups/${groupUuid}/members/${userId}`, {
    method: 'DELETE',
  })
}

export function searchUsersForGroup(query: string) {
  return apiFetch<{ users: { user_id: string; name: string | null; email: string | null }[] }>(
    `/api/verification/groups/search-users?q=${encodeURIComponent(query)}`,
  )
}
