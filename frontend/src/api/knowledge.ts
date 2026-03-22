import { apiFetch } from './client'
import type { KnowledgeBase, KnowledgeBaseDetail } from '../types/knowledge'

export function listKnowledgeBases() {
  return apiFetch<KnowledgeBase[]>('/api/knowledge/list')
}

export function createKnowledgeBase(title: string, description?: string) {
  return apiFetch<KnowledgeBase>('/api/knowledge/create', {
    method: 'POST',
    body: JSON.stringify({ title, description }),
  })
}

export function getKnowledgeBase(uuid: string) {
  return apiFetch<KnowledgeBaseDetail>(`/api/knowledge/${uuid}`)
}

export function updateKnowledgeBase(uuid: string, data: { title?: string; description?: string }) {
  return apiFetch<{ ok: boolean }>(`/api/knowledge/${uuid}/update`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function deleteKnowledgeBase(uuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/knowledge/${uuid}`, { method: 'DELETE' })
}

export function addDocumentsToKB(uuid: string, documentUuids: string[]) {
  return apiFetch<{ ok: boolean; added: number }>(`/api/knowledge/${uuid}/add_documents`, {
    method: 'POST',
    body: JSON.stringify({ document_uuids: documentUuids }),
  })
}

export function addUrlsToKB(
  uuid: string,
  urls: string[],
  crawlEnabled = false,
  maxCrawlPages = 5,
  allowedDomains = '',
) {
  return apiFetch<{ ok: boolean; added: number }>(`/api/knowledge/${uuid}/add_urls`, {
    method: 'POST',
    body: JSON.stringify({
      urls,
      crawl_enabled: crawlEnabled,
      max_crawl_pages: maxCrawlPages,
      allowed_domains: allowedDomains,
    }),
  })
}

export function removeKBSource(uuid: string, sourceUuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/knowledge/${uuid}/source/${sourceUuid}`, {
    method: 'DELETE',
  })
}

export function shareKnowledgeBase(uuid: string) {
  return apiFetch<{ ok: boolean; shared_with_team: boolean }>(`/api/knowledge/${uuid}/share`, {
    method: 'POST',
  })
}

export function submitKBForVerification(kbUuid: string, data: {
  summary?: string
  description?: string
  category?: string
}) {
  return apiFetch<Record<string, unknown>>('/api/verify/submit', {
    method: 'POST',
    body: JSON.stringify({
      item_kind: 'knowledge_base',
      item_id: kbUuid,
      ...data,
    }),
  })
}

export function setKBOrganizations(uuid: string, organizationIds: string[]) {
  return apiFetch<{ ok: boolean }>(`/api/knowledge/${uuid}/update`, {
    method: 'POST',
    body: JSON.stringify({ organization_ids: organizationIds }),
  })
}

export function getKBStatus(uuid: string) {
  return apiFetch<{
    uuid: string
    status: string
    total_sources: number
    sources_ready: number
    sources_failed: number
    total_chunks: number
    sources: { uuid: string; status: string; error_message: string; chunk_count: number }[]
  }>(`/api/knowledge/${uuid}/status`)
}

// Validation

export function runKBValidation(uuid: string) {
  return apiFetch<Record<string, unknown>>(`/api/knowledge/${uuid}/validate`, {
    method: 'POST',
  })
}

export function getKBSourceHealth(uuid: string) {
  return apiFetch<{
    total: number
    healthy: number
    unhealthy: number
    ratio: number
    details: { uuid: string; source_type: string; name: string; status: string; error?: string }[]
  }>(`/api/knowledge/${uuid}/source-health`)
}

export function getKBQuality(uuid: string) {
  return apiFetch<{
    history: Record<string, unknown>[]
    contract: Record<string, unknown>
  }>(`/api/knowledge/${uuid}/quality`)
}

// Test queries

export function listKBTestQueries(uuid: string) {
  return apiFetch<{
    test_queries: {
      uuid: string
      query: string
      expected_source_labels: string[]
      expected_answer_contains: string | null
      created_at: string | null
    }[]
  }>(`/api/knowledge/${uuid}/test-queries`)
}

export function createKBTestQuery(uuid: string, data: {
  query: string
  expected_source_labels?: string[]
  expected_answer_contains?: string
}) {
  return apiFetch<Record<string, unknown>>(`/api/knowledge/${uuid}/test-queries`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function deleteKBTestQuery(uuid: string, queryUuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/knowledge/${uuid}/test-queries/${queryUuid}`, {
    method: 'DELETE',
  })
}

// Clone

export function cloneKnowledgeBase(uuid: string, title?: string) {
  return apiFetch<Record<string, unknown>>(`/api/knowledge/${uuid}/clone`, {
    method: 'POST',
    body: JSON.stringify({ title }),
  })
}

// Suggestions

export function submitKBSuggestion(uuid: string, data: {
  suggestion_type: string
  url?: string
  document_uuid?: string
  note?: string
}) {
  return apiFetch<Record<string, unknown>>(`/api/knowledge/${uuid}/suggestions`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function listKBSuggestions(uuid: string) {
  return apiFetch<{
    suggestions: {
      uuid: string
      suggestion_type: string
      url: string | null
      document_uuid: string | null
      note: string | null
      status: string
      suggested_by_name: string | null
      suggested_by_user_id: string
      reviewed_by_user_id: string | null
      reviewed_at: string | null
      created_at: string | null
    }[]
  }>(`/api/knowledge/${uuid}/suggestions`)
}

export function reviewKBSuggestion(kbUuid: string, suggestionUuid: string, accept: boolean) {
  return apiFetch<Record<string, unknown>>(`/api/knowledge/${kbUuid}/suggestions/${suggestionUuid}`, {
    method: 'PATCH',
    body: JSON.stringify({ accept }),
  })
}
