export interface SurveyField {
  key: string
  label: string
  type: 'text' | 'textarea' | 'select' | 'number' | 'multiselect' | 'likert_group' | 'info'
  required: boolean
  placeholder?: string
  options?: string[]
  /** For likert_group: the individual statements to rate */
  statements?: { key: string; label: string }[]
  /** Visual section grouping label */
  section?: string
}

export interface PostExperienceRequest {
  responses: Record<string, unknown>
}

export interface FeedbackInfo {
  name: string
  organization: string
  already_completed: boolean
}

export interface TrialEndInfo {
  name: string
  organization: string
  engagement: 'low' | 'engaged'
  extensions_used: number
  max_extensions: number
  can_self_extend: boolean
  already_extended: boolean
  /** Token balance when the screen was opened, and what a top-up adds. */
  tokens_used: number
  tokens_budget: number
  topup_tokens: number
}

/** Trial token balance. When `enabled` is false, render nothing at all. */
export interface TrialUsage {
  enabled: boolean
  budget: number
  used: number
  remaining: number
  percent: number
  /** False means AI features are gated until the address is confirmed. */
  email_verified: boolean
}

export interface TrialExtensionResult {
  ok: boolean
  message: string
  /** Tokens added by this top-up, and the account's new lifetime ceiling. */
  tokens_granted?: number | null
  tokens_budget?: number | null
  /** One-time magic sign-in URL — the topped-up account's way back in. */
  login_url?: string | null
}

export interface DemoApplication {
  uuid: string
  name: string
  title: string
  email: string
  organization: string
  status: string
  waitlist_position: number | null
  activated_at: string | null
  expires_at: string | null
  tokens_used: number
  tokens_budget: number
  post_questionnaire_completed: boolean
  admin_released: boolean
  created_at: string
  questionnaire_responses: Record<string, unknown>
  credentials_sent_at: string | null
  last_login_at: string | null
  user_is_demo: boolean
}

export interface DemoAdminStats {
  total_applications: number
  active_count: number
  waitlist_count: number
  expired_count: number
  completed_count: number
  by_organization: { organization: string; count: number }[]
}

export interface PostExperienceResponseAdmin {
  uuid: string
  name: string
  email: string
  organization: string
  title: string
  questionnaire_responses: Record<string, unknown>
  responses: Record<string, unknown>
  created_at: string
}
