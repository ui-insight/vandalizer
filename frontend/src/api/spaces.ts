import { apiFetch } from './client'

export interface Space {
  id: string
  uuid: string
  title: string
  user: string | null
}

export function listSpaces() {
  return apiFetch<Space[]>('/api/spaces/')
}

export function createSpace(title: string) {
  return apiFetch<Space>('/api/spaces/create', { method: 'POST', body: JSON.stringify({ title }) })
}

export function updateSpace(uuid: string, data: { title?: string }) {
  return apiFetch<Space>(`/api/spaces/${uuid}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export function deleteSpace(uuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/spaces/${uuid}`, { method: 'DELETE' })
}
