import { apiFetch } from './client'
import type { ActivityEvent } from '../types/chat'

export function getActivity(activityId: string) {
  return apiFetch<{ activity: ActivityEvent }>(`/api/activity/${activityId}`)
}

/** Rename a chat; the name shows in the activity list and on the chat. */
export function renameActivity(activityId: string, title: string) {
  return apiFetch<{ activity: ActivityEvent }>(`/api/activity/${activityId}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  })
}

export function deleteActivity(activityId: string) {
  return apiFetch<{ status: string; message: string }>(`/api/activity/${activityId}`, {
    method: 'DELETE',
  })
}

export function listActivities(limit: number = 50) {
  return apiFetch<{ events: ActivityEvent[]; stale_threshold_minutes: number }>(
    `/api/activity/streams/?limit=${limit}`,
  )
}
