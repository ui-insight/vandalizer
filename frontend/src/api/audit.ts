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
