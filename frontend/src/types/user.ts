export type RoleSegment =
  | 'research_admin'
  | 'pi'
  | 'sponsored_programs'
  | 'compliance'
  | 'it'
  | 'other'

export const ROLE_SEGMENT_LABELS: Record<RoleSegment, string> = {
  research_admin: 'Research administrator',
  pi: 'Principal investigator',
  sponsored_programs: 'Sponsored programs',
  compliance: 'Research compliance',
  it: 'IT / systems',
  other: 'Other',
}

export interface User {
  id: string
  user_id: string
  email: string | null
  name: string | null
  is_admin: boolean
  is_staff: boolean
  is_examiner: boolean
  is_support_agent: boolean
  is_demo_user: boolean
  current_team: string | null
  current_team_uuid: string | null
  role_segment: RoleSegment | null
}

export interface Team {
  id: string
  uuid: string
  name: string
  owner_user_id: string
  role: string | null
}

export interface TeamMember {
  user_id: string
  role: string
  name: string | null
  email: string | null
}

export interface TeamInvite {
  id: string
  email: string
  role: string
  accepted: boolean
  token: string
  created_at: string | null
}

export interface TeamJoinLink {
  id: string
  token: string
  role: string
  expires_at: string | null
  max_uses: number | null
  use_count: number
  revoked: boolean
  created_at: string | null
  created_by_user_id: string
}
