import { apiFetch } from './client'

export function uploadFile(data: {
  contentAsBase64String: string
  fileName: string
  extension: string
  space: string
  folder?: string
}) {
  return apiFetch<{ complete: boolean; uuid?: string; exists?: boolean }>(
    '/api/files/upload',
    { method: 'POST', body: JSON.stringify(data) },
  )
}

export function deleteFile(docUuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/files/${docUuid}`, { method: 'DELETE' })
}

export function renameFile(uuid: string, newName: string) {
  return apiFetch<{ ok: boolean }>('/api/files/rename', {
    method: 'PATCH',
    body: JSON.stringify({ uuid, newName }),
  })
}

export function moveFile(fileUUID: string, folderID: string) {
  return apiFetch<{ ok: boolean }>('/api/files/move', {
    method: 'PATCH',
    body: JSON.stringify({ fileUUID, folderID }),
  })
}

export function downloadFileUrl(docid: string) {
  return `/api/files/download?docid=${docid}`
}
