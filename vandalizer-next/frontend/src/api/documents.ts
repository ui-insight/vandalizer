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
