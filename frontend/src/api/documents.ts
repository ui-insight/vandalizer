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
}

export function searchDocuments(query: string = '', limit: number = 20, folder?: string | null) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (query) params.set('q', query)
  if (folder !== undefined && folder !== null) params.set('folder', folder)
  return apiFetch<{ items: SearchResult[]; total: number }>(
    `/api/documents/search?${params}`
  )
}
