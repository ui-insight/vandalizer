import { apiFetch } from './client'
import type { ListContentsResponse, PollStatusResponse } from '../types/document'

export function listContents(space: string, folder?: string, teamUuid?: string) {
  const params = new URLSearchParams({ space })
  if (folder) params.set('folder', folder)
  if (teamUuid) params.set('team_uuid', teamUuid)
  return apiFetch<ListContentsResponse>(`/api/documents/list?${params}`)
}

export function pollStatus(docid: string) {
  return apiFetch<PollStatusResponse>(`/api/documents/poll_status?docid=${docid}`)
}

export interface SearchResult {
  uuid: string
  title: string
  extension: string
  snippet: string
  num_pages: number
  created_at: string | null
}

export function searchDocuments(query: string, limit: number = 20) {
  return apiFetch<{ items: SearchResult[]; total: number }>(
    `/api/documents/search?q=${encodeURIComponent(query)}&limit=${limit}`
  )
}
