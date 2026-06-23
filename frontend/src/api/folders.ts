import { apiFetch, rawFetch } from './client'
import type { Folder } from '../types/document'

export function createFolder(data: { name: string; parent_id: string; folder_type?: string }) {
  return apiFetch<Folder>('/api/folders/create', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function renameFolder(uuid: string, newName: string) {
  return apiFetch<{ ok: boolean }>('/api/folders/rename', {
    method: 'PATCH',
    body: JSON.stringify({ uuid, newName }),
  })
}

export function deleteFolder(folderUuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/folders/${folderUuid}`, { method: 'DELETE' })
}

export function moveFolder(folderUuid: string, parentId: string) {
  return apiFetch<Folder>(`/api/folders/${folderUuid}/move`, {
    method: 'PATCH',
    body: JSON.stringify({ parent_id: parentId }),
  })
}

export async function exportFolder(folderUuid: string, fallbackName = 'folder') {
  const res = await rawFetch(`/api/folders/${folderUuid}/export`)
  if (!res.ok) throw new Error('Export failed')
  // Honor the server-provided filename, falling back to the folder title.
  const disposition = res.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="?([^"]+)"?/)
  const filename = match?.[1] || `${fallbackName}.zip`
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function convertFolderToTeam(folderUuid: string) {
  return apiFetch<Folder>(`/api/folders/${folderUuid}/convert-to-team`, { method: 'PATCH' })
}

export function getBreadcrumbs(folderUuid: string) {
  return apiFetch<Array<{ uuid: string; title: string }>>(
    `/api/folders/breadcrumbs/${folderUuid}`,
  )
}

export interface FolderSummary {
  uuid: string
  title: string
  path: string
  parent_id: string
  is_shared_team_root: boolean
  team_id: string | null
}

export function listAllFolders() {
  return apiFetch<FolderSummary[]>('/api/folders/all')
}
