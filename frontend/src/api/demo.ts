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

export function resendCredentials(uuid: string) {
  return apiFetch<{ ok: boolean; message: string }>(`/api/demo/resend-credentials/${uuid}`, {
    method: 'POST',
  })
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

export function restartDemoTrial(demoUuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/demo/admin/restart-trial/${demoUuid}`, { method: 'POST' })
}

export function activateDemoUser(demoUuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/demo/admin/activate/${demoUuid}`, { method: 'POST' })
}

export function getPostExperienceResponses() {
  return apiFetch<PostExperienceResponseAdmin[]>('/api/demo/admin/responses')
}

export function sendTestEmail(to: string) {
  return apiFetch<{ ok: boolean; message: string }>(`/api/demo/admin/test-email?to=${encodeURIComponent(to)}`, {
    method: 'POST',
  })
}

export function adminResendCredentials(demoUuid: string) {
  return apiFetch<{ ok: boolean; message: string }>(`/api/demo/resend-credentials/${demoUuid}`, {
    method: 'POST',
  })
}

export function adminAddDemoUser(data: { first_name: string; last_name: string; email: string }) {
  return apiFetch<{ ok: boolean; uuid: string }>('/api/demo/admin/add-user', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function adminGetMagicLink(demoUuid: string) {
  return apiFetch<{ ok: boolean; url: string }>(`/api/demo/admin/magic-link/${demoUuid}`, {
    method: 'POST',
  })
}
