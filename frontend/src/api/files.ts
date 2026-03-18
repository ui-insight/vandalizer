import { apiFetch, csrfHeaders } from './client'

export function uploadFile(data: {
  contentAsBase64String: string
  fileName: string
  extension: string
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

export function downloadFile(docid: string) {
  const a = document.createElement('a')
  a.href = downloadFileUrl(docid)
  a.download = ''
  document.body.appendChild(a)
  a.click()
  a.remove()
}

export async function downloadFilesAsZip(docIds: string[]) {
  const res = await fetch('/api/files/download-bulk', {
    method: 'POST',
    credentials: 'include',
    headers: csrfHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ doc_ids: docIds }),
  })
  if (!res.ok) throw new Error('Download failed')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'documents.zip'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
