import { getCsrfToken } from './client'

export type JourneyEvent = 'initial_progress_load_failed' | 'progress_refresh_failed' | 'position_save_failed'
  | 'saved_lesson_displayed' | 'bridge_assessment_requested'
type Identity = { enrollment_id?: string; manifest_sha256?: string }

/** Best effort local operations telemetry. No answers, errors, titles or documents. */
export function observeCertificationJourney(event: JourneyEvent, identity?: Identity | null): void {
  try {
    const bound = identity?.enrollment_id && identity.manifest_sha256
    if (!bound && event !== 'initial_progress_load_failed' && event !== 'progress_refresh_failed') return
    const eventId = crypto.randomUUID().replaceAll('-', '')
    const csrf = getCsrfToken()
    // The normal API wrappers can reload a tab to recover CSRF. Optional
    // telemetry must never trigger that behavior or retry a learner action.
    void fetch('/api/certification/journey-events', { method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) }, body: JSON.stringify({
      event_id: eventId, event,
      ...(bound ? { enrollment_id: identity.enrollment_id, manifest_sha256: identity.manifest_sha256 } : {}),
    }), signal: AbortSignal.timeout(3000) }).catch(() => { /* Telemetry cannot interrupt learning; no automatic retries. */ })
  } catch { /* Unavailable UUID, network, or browser API must not affect course actions. */ }
}
