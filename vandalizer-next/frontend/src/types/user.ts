export interface User {
  id: string
  user_id: string
  email: string | null
  name: string | null
  is_admin: boolean
  current_team: string | null
  current_team_uuid: string | null
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
}
