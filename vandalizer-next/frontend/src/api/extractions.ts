import { apiFetch } from './client'
import type { SearchSet, SearchSetItem } from '../types/workflow'

// SearchSet CRUD

export function createSearchSet(data: { title: string; space: string; set_type?: string; extraction_config?: Record<string, unknown> }) {
  return apiFetch<SearchSet>('/api/extractions/search-sets', {
    method: 'POST',
    body: JSON.stringify({ set_type: 'extraction', ...data }),
  })
}

export function listSearchSets(space?: string) {
  const params = space ? `?space=${encodeURIComponent(space)}` : ''
  return apiFetch<SearchSet[]>(`/api/extractions/search-sets${params}`)
}

export function getSearchSet(uuid: string) {
  return apiFetch<SearchSet>(`/api/extractions/search-sets/${uuid}`)
}

export function updateSearchSet(uuid: string, data: { title?: string; extraction_config?: Record<string, unknown> }) {
  return apiFetch<SearchSet>(`/api/extractions/search-sets/${uuid}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteSearchSet(uuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/extractions/search-sets/${uuid}`, { method: 'DELETE' })
}

export function cloneSearchSet(uuid: string) {
  return apiFetch<SearchSet>(`/api/extractions/search-sets/${uuid}/clone`, { method: 'POST' })
}

// Items

export function addItem(searchSetUuid: string, data: { searchphrase: string; searchtype?: string; title?: string }) {
  return apiFetch<SearchSetItem>(`/api/extractions/search-sets/${searchSetUuid}/items`, {
    method: 'POST',
    body: JSON.stringify({ searchtype: 'extraction', ...data }),
  })
}

export function listItems(searchSetUuid: string) {
  return apiFetch<SearchSetItem[]>(`/api/extractions/search-sets/${searchSetUuid}/items`)
}

export function deleteItem(itemId: string) {
  return apiFetch<{ ok: boolean }>(`/api/extractions/items/${itemId}`, { method: 'DELETE' })
}

// Run extraction

export function runExtractionSync(data: {
  search_set_uuid: string
  document_uuids: string[]
  model?: string
  extraction_config_override?: Record<string, unknown>
}) {
  return apiFetch<{ results: unknown[] }>('/api/extractions/run-sync', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}
