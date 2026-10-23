import { apiFetch } from './client'

export interface AuditLogEntry {
  uuid: string
  timestamp: string | null
  actor_user_id: string
  actor_type: string
  action: string
  resource_type: string
  resource_id: string | null
  resource_name: string | null
  team_id: string | null
  organization_id: string | null
  detail: Record<string, unknown>
  ip_address: string | null
}

export interface AuditLogResponse {
  entries: AuditLogEntry[]
  total: number
  skip: number
  limit: number
}

export function queryAuditLog(params: {
  action?: string
  actor_user_id?: string
  resource_type?: string
  resource_id?: string
  organization_id?: string
  start_time?: string
  end_time?: string
  skip?: number
  limit?: number
}): Promise<AuditLogResponse> {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) qs.set(k, String(v))
  })
  return apiFetch(`/api/audit/?${qs.toString()}`)
}

export function exportAuditLog(params?: {
  action?: string
  actor_user_id?: string
  resource_type?: string
  start_time?: string
  end_time?: string
}): string {
  const qs = new URLSearchParams()
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v) qs.set(k, v)
    })
  }
  return `/api/audit/export?${qs.toString()}`
}

// Web searches sent to the deployment's search provider (web_search_usage).

export interface WebSearchEntry {
  id: string
  timestamp: string | null
  feature: string
  user_id: string | null
  team_id: string | null
  activity_id: string | null
  provider: string | null
  query: string
  result_count: number
  status: 'ok' | 'error' | 'not_configured' | string
  error: string | null
}

export interface WebSearchResponse {
  entries: WebSearchEntry[]
  total: number
  skip: number
  limit: number
  by_feature: Record<string, number>
  by_status: Record<string, number>
}

export interface WebSearchFilters {
  feature?: string
  status?: string
  provider?: string
  user_id?: string
  start_time?: string
  end_time?: string
}

function webSearchQuery(params: WebSearchFilters & { skip?: number; limit?: number }): string {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  })
  return qs.toString()
}

export function queryWebSearches(params: WebSearchFilters & { skip?: number; limit?: number }): Promise<WebSearchResponse> {
  return apiFetch(`/api/audit/web-searches?${webSearchQuery(params)}`)
}

export function exportWebSearches(params: WebSearchFilters = {}): string {
  return `/api/audit/web-searches/export?${webSearchQuery(params)}`
}
