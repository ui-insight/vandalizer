import { apiFetch } from './client'
import type { ListContentsResponse, PollStatusResponse } from '../types/document'

export function listContents(folder?: string, teamUuid?: string) {
  const params = new URLSearchParams()
  if (folder) params.set('folder', folder)
  if (teamUuid) params.set('team_uuid', teamUuid)
  const query = params.toString()
  return apiFetch<ListContentsResponse>(`/api/documents/list${query ? `?${query}` : ''}`)
}

export function pollStatus(docid: string) {
  return apiFetch<PollStatusResponse>(`/api/documents/poll_status?docid=${docid}`)
}

/** Stop an in-flight extraction (e.g. a stuck OCR read). The document is
 *  left in a retryable error state, so `retryExtraction` restarts it. */
export function cancelExtraction(docUuid: string) {
  // restored_previous_text: the stopped run was a re-read, and the document
  // has the text it had before.
  return apiFetch<{ uuid: string; status: string; restored_previous_text?: boolean }>(
    `/api/documents/${docUuid}/cancel-extraction`,
    { method: 'POST' }
  )
}

/** Re-run text extraction. `forceOcr` re-reads a PDF with OCR even when its
 *  current text looks healthy (the "Re-run OCR" action). */
export function retryExtraction(docUuid: string, opts: { forceOcr?: boolean } = {}) {
  const query = opts.forceOcr ? '?force_ocr=true' : ''
  return apiFetch<{ uuid: string; task_id: string; status: string }>(
    `/api/documents/${docUuid}/retry-extraction${query}`,
    { method: 'POST' }
  )
}

export interface SearchResult {
  uuid: string
  title: string
  extension: string
  snippet: string
  num_pages: number
  created_at: string | null
  updated_at: string | null
  processing: boolean
  valid: boolean
  task_status: string | null
  folder: string | null
  token_count: number
  extraction_low_quality?: boolean
  ingestion_warnings?: string[]
  ingestion_warning_text?: string
}

export function searchDocuments(query: string = '', limit: number = 20, folder?: string | null) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (query) params.set('q', query)
  if (folder !== undefined && folder !== null) params.set('folder', folder)
  return apiFetch<{ items: SearchResult[]; total: number }>(
    `/api/documents/search?${params}`
  )
}

/** Titles of the documents and folders the caller can view; the rest are left out. */
export function resolveTitles(documentUuids: string[], folderUuids: string[]) {
  return apiFetch<{
    documents: { uuid: string; title: string }[]
    folders: { uuid: string; title: string }[]
  }>('/api/documents/titles', {
    method: 'POST',
    body: JSON.stringify({ document_uuids: documentUuids, folder_uuids: folderUuids }),
  })
}
