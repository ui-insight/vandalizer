import { apiFetch } from './client'

export interface Notification {
  id: string
  uuid: string
  kind: string
  title: string
  body: string | null
  link: string | null
  item_kind: string | null
  item_id: string | null
  item_name: string | null
  request_uuid: string | null
  read: boolean
  created_at: string | null
}

export function listNotifications(unreadOnly = false, limit = 50) {
  const params = new URLSearchParams()
  if (unreadOnly) params.set('unread_only', 'true')
  params.set('limit', String(limit))
  return apiFetch<{ notifications: Notification[]; unread_count: number }>(
    `/api/notifications?${params}`,
  )
}

export function getUnreadCount() {
  return apiFetch<{ unread_count: number }>('/api/notifications/count')
}

export function markRead(notificationUuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/notifications/${notificationUuid}/read`, {
    method: 'POST',
  })
}

export function markReadForItem(itemKind: string, itemId: string) {
  return apiFetch<{ ok: boolean; marked_count: number }>(
    `/api/notifications/read-item/${itemKind}/${itemId}`,
    { method: 'POST' },
  )
}

export function markAllRead() {
  return apiFetch<{ ok: boolean; marked_count: number }>('/api/notifications/read-all', {
    method: 'POST',
  })
}
