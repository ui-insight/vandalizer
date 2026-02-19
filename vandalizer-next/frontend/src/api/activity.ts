import { apiFetch } from './client'
import type { ActivityEvent } from '../types/chat'

export function getActivity(activityId: string) {
  return apiFetch<{ activity: ActivityEvent }>(`/api/activity/${activityId}`)
}

export function deleteActivity(activityId: string) {
  return apiFetch<{ status: string; message: string }>(`/api/activity/${activityId}`, {
    method: 'DELETE',
  })
}

export function listActivities(limit: number = 50) {
  return apiFetch<{ events: ActivityEvent[] }>(`/api/activity/streams/?limit=${limit}`)
}
