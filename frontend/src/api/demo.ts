import { apiFetch } from './client'
import type {
  DemoSignupRequest,
  DemoSignupResponse,
  WaitlistStatusResponse,
  FeedbackInfo,
  DemoAdminStats,
  DemoApplication,
  PostExperienceResponseAdmin,
} from '../types/demo'

// ---------------------------------------------------------------------------
// Public endpoints (no auth required)
// ---------------------------------------------------------------------------

export function submitDemoApplication(data: DemoSignupRequest) {
  return apiFetch<DemoSignupResponse>('/api/demo/apply', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function getWaitlistStatus(uuid: string) {
  return apiFetch<WaitlistStatusResponse>(`/api/demo/status/${uuid}`)
}

export function getPostQuestionnaire(token: string) {
  return apiFetch<FeedbackInfo>(`/api/demo/feedback/${token}`)
}

export function submitPostQuestionnaire(token: string, responses: Record<string, unknown>) {
  return apiFetch<{ message: string }>(`/api/demo/feedback/${token}`, {
    method: 'POST',
    body: JSON.stringify({ responses }),
  })
}

// ---------------------------------------------------------------------------
// Admin endpoints (require auth + is_admin)
// ---------------------------------------------------------------------------

export function getDemoStats() {
  return apiFetch<DemoAdminStats>('/api/demo/admin/stats')
}

export function getDemoApplications(status?: string) {
  const params = status ? `?status=${encodeURIComponent(status)}` : ''
  return apiFetch<DemoApplication[]>(`/api/demo/admin/applications${params}`)
}

export function releaseDemoUser(demoUuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/demo/admin/release/${demoUuid}`, { method: 'POST' })
}

export function activateDemoUser(demoUuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/demo/admin/activate/${demoUuid}`, { method: 'POST' })
}

export function getPostExperienceResponses() {
  return apiFetch<PostExperienceResponseAdmin[]>('/api/demo/admin/responses')
}
