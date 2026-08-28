import { apiFetch, rawFetch } from './client'

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

export function downloadFileUrl(docid: string, options?: { inline?: boolean }) {
  const base = `/api/files/download?docid=${encodeURIComponent(docid)}`
  return options?.inline ? `${base}&inline=1` : base
}

export interface SheetJsonResponse {
  sheets: Array<{
    name: string
    headers: string[]
    rows: string[][]
    hidden: boolean
  }>
}

export function fetchSheetJson(docUuid: string) {
  return apiFetch<SheetJsonResponse>(`/api/files/${docUuid}/sheet-json`)
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
  const res = await rawFetch('/api/files/download-bulk', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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

/** Everything that references a document — see backend document_usage.py. */
export interface DocumentUsage {
  document: { uuid: string; title: string }
  folder: { path: { uuid: string; title: string }[]; team_id: string | null }
  knowledge_bases: { uuid: string; title: string; exists: boolean }[]
  extractions: {
    uuid: string; title: string; exists: boolean
    test_cases: { uuid: string; label: string }[]
  }[]
  workflows: {
    id: string; name: string
    uses: { kind: 'fixed_document' | 'step_document'; step?: string; task?: string; role?: string }[]
  }[]
  total: number
}

export function fetchDocumentUsage(docUuid: string) {
  return apiFetch<DocumentUsage>(`/api/files/${docUuid}/usage`)
}
