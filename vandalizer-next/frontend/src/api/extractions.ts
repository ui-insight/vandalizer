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

export function updateItem(itemId: string, data: { searchphrase?: string; title?: string }) {
  return apiFetch<SearchSetItem>(`/api/extractions/items/${itemId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteItem(itemId: string) {
  return apiFetch<{ ok: boolean }>(`/api/extractions/items/${itemId}`, { method: 'DELETE' })
}

// Reorder items

export function reorderItems(searchSetUuid: string, itemIds: string[]) {
  return apiFetch<{ ok: boolean }>(`/api/extractions/search-sets/${searchSetUuid}/reorder-items`, {
    method: 'POST',
    body: JSON.stringify({ item_ids: itemIds }),
  })
}

// Build from document (AI field generation)

export function buildFromDocument(searchSetUuid: string, documentUuids: string[], model?: string) {
  return apiFetch<{ entities: string[] }>(`/api/extractions/search-sets/${searchSetUuid}/build-from-document`, {
    method: 'POST',
    body: JSON.stringify({ document_uuids: documentUuids, model }),
  })
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

// Test cases

export interface TestCase {
  id: string
  uuid: string
  search_set_uuid: string
  label: string
  source_type: string
  source_text?: string | null
  document_uuid?: string | null
  expected_values: Record<string, string>
  user_id: string
  created_at: string
}

export interface FieldValidationResult {
  field_name: string
  expected: string | null
  extracted_values: (string | null)[]
  most_common_value: string | null
  consistency: number
  accuracy: number | null
  accuracy_method: string | null
}

export interface TestCaseValidationResult {
  test_case_uuid: string
  label: string
  fields: FieldValidationResult[]
  overall_accuracy: number | null
  overall_consistency: number
}

export interface ValidationResult {
  search_set_uuid: string
  num_runs: number
  test_cases: TestCaseValidationResult[]
  aggregate_accuracy: number | null
  aggregate_consistency: number
}

export function createTestCase(data: {
  search_set_uuid: string
  label: string
  source_type: string
  source_text?: string
  document_uuid?: string
  expected_values: Record<string, string>
}) {
  return apiFetch<TestCase>('/api/extractions/test-cases', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function listTestCases(searchSetUuid: string) {
  return apiFetch<TestCase[]>(`/api/extractions/test-cases?search_set_uuid=${encodeURIComponent(searchSetUuid)}`)
}

export function updateTestCase(uuid: string, data: {
  label?: string
  source_type?: string
  source_text?: string
  document_uuid?: string
  expected_values?: Record<string, string>
}) {
  return apiFetch<TestCase>(`/api/extractions/test-cases/${uuid}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteTestCase(uuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/extractions/test-cases/${uuid}`, { method: 'DELETE' })
}

export function runValidation(data: {
  search_set_uuid: string
  test_case_uuids?: string[]
  num_runs?: number
  model?: string
}) {
  return apiFetch<ValidationResult>('/api/extractions/validate', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}
