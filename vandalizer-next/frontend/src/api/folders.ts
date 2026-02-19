import { apiFetch } from './client'
import type { Folder } from '../types/document'

export function createFolder(data: { name: string; parent_id: string; space: string; folder_type?: string }) {
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

export function getBreadcrumbs(folderUuid: string) {
  return apiFetch<Array<{ uuid: string; title: string }>>(
    `/api/folders/breadcrumbs/${folderUuid}`,
  )
}
