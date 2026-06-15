export type ProjectState =
  | 'draft'
  | 'active'
  | 'submitted'
  | 'awarded'
  | 'closeout'
  | 'archived'

export const PROJECT_STATES: ProjectState[] = [
  'draft',
  'active',
  'submitted',
  'awarded',
  'closeout',
  'archived',
]

export interface Project {
  uuid: string
  title: string
  description: string | null
  owner_user_id: string
  team_id: string | null
  state: ProjectState
  root_folder_uuid: string
  kb_uuid: string | null
  created_at: string
  updated_at: string
  // Present on list responses (`GET /api/projects`) so explorer cards can show
  // what's inside, and which manage actions to offer, without a per-project
  // overview fetch. Omitted on create/update responses.
  capabilities?: ProjectCapabilities
  role?: ProjectRole
}

export interface ProjectCapabilities {
  files: { count: number; folders: number }
  knowledge: { ready: boolean; documents: number }
  workflows: { count: number }
  extractions: { count: number }
  automations: { count: number }
  external_kbs: { count: number }
  members: { count: number }
}

export type ProjectRole = 'owner' | 'editor' | 'viewer' | 'none'

export interface ProjectOverview extends Project {
  role: ProjectRole
  capabilities: ProjectCapabilities
}

export interface ProjectMember {
  user_id: string
  role: string
  name: string | null
  email: string | null
}

export interface ProjectInviteLink {
  token: string
  role: string
  expires_at: string | null
  revoked: boolean
  use_count: number
  created_at: string | null
}

export interface ProjectPin {
  pin_type: string // workflow | extraction | automation | knowledge_base
  target_id: string
  name: string
}

export interface ProjectInviteInfo {
  role: string
  project_title: string
  project_uuid: string | null
  inviter_name: string | null
  status: string | null // null = usable; else revoked|expired|exhausted
}
