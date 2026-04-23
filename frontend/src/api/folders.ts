import { apiFetch } from './client'
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
