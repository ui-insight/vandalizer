export type CredentialType = 'static_header' | 'oauth_client_credentials'

export interface Credential {
  id: string
  name: string
  type: CredentialType
  description: string | null
  team_id: string | null
  user_id: string
  payload: Record<string, string>
  created_at: string | null
  updated_at: string | null
  can_manage: boolean
  /** On an update that changed the type: API steps re-pointed to it. */
  steps_updated?: number | null
}

/** One step of a credential connection test. */
export interface CredentialTestStep { step: string; ok: boolean; detail: string }

export interface CredentialTestResult {
  ok: boolean
  steps: CredentialTestStep[]
  status_code: number | null
  elapsed_ms: number | null
}
