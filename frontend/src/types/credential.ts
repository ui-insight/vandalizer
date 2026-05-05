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
}
