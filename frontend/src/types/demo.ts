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

export interface DemoSignupRequest {
  name: string
  title: string
  email: string
  organization: string
  questionnaire_responses: Record<string, unknown>
}

export interface DemoSignupResponse {
  uuid: string
  waitlist_position: number
  message: string
}

export interface WaitlistStatusResponse {
  uuid: string
  status: string
  waitlist_position: number | null
  estimated_wait: string | null
}

export interface PostExperienceRequest {
  responses: Record<string, unknown>
}

export interface FeedbackInfo {
  name: string
  organization: string
  already_completed: boolean
}

export interface DemoApplication {
  uuid: string
  name: string
  email: string
  organization: string
  status: string
  waitlist_position: number | null
  activated_at: string | null
  expires_at: string | null
  post_questionnaire_completed: boolean
  admin_released: boolean
  created_at: string
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
