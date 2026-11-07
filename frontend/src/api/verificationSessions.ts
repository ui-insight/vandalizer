import { apiFetch } from './client'

export type VerificationFieldStatus = 'pending' | 'approved' | 'corrected' | 'skipped'

export interface VerificationSessionField {
  key: string
  extracted: string
  expected: string | null
  status: VerificationFieldStatus
}

export interface VerificationSession {
  uuid: string
  search_set_uuid: string
  document_uuid: string
  document_title: string
  label: string
  status: 'pending' | 'completed' | 'cancelled'
  test_case_uuid: string | null
  fields: VerificationSessionField[]
  all_resolved: boolean
  created_at: string | null
  updated_at: string | null
}

export interface FinalizeResponse {
  session: VerificationSession
  test_case: {
    uuid: string
    label: string
    search_set_uuid: string
    expected_values: Record<string, string>
  }
}

export async function getVerificationSession(uuid: string): Promise<VerificationSession> {
  return apiFetch(`/api/verification-sessions/${uuid}`)
}

export async function patchVerificationField(
  uuid: string,
  key: string,
  body: { status: VerificationFieldStatus; expected?: string },
): Promise<VerificationSession> {
  return apiFetch(`/api/verification-sessions/${uuid}/fields/${encodeURIComponent(key)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export async function finalizeVerificationSession(
  uuid: string,
  label?: string,
): Promise<FinalizeResponse> {
  return apiFetch(`/api/verification-sessions/${uuid}/finalize`, {
    method: 'POST',
    body: JSON.stringify({ label: label ?? null }),
  })
}

export async function cancelVerificationSession(uuid: string): Promise<VerificationSession> {
  return apiFetch(`/api/verification-sessions/${uuid}/cancel`, {
    method: 'POST',
  })
}
