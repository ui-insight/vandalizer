export type TriggerType = 'folder_watch' | 'm365_intake' | 'api' | 'schedule'
export type ActionType = 'workflow' | 'extraction' | 'task'

export interface Automation {
  id: string
  name: string
  description: string | null
  enabled: boolean
  trigger_type: TriggerType
  trigger_config: Record<string, unknown>
  action_type: ActionType
  action_id: string | null
  user_id: string
  team_id: string | null
  shared_with_team: boolean
  space: string | null
  created_at: string
  updated_at: string
}
