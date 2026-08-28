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
  action_name: string | null
  user_id: string
  team_id: string | null
  shared_with_team: boolean
  output_config: Record<string, unknown>
  created_at: string
  updated_at: string
  can_manage: boolean
}

/** Response of POST /api/automations/{id}/run-now. */
export interface RunNowResponse {
  status: string
  trigger_event_id: string
  action_type: string
  documents: { uuid: string; title: string }[]
  document_source: 'chosen' | 'folder' | 'configured'
  documents_matched: number
}

/** GET /api/automations/{id}/runs/{event_id} — the same shape the API-key route returns. */
export interface AutomationRunStatus {
  trigger_event_id: string
  status: 'pending' | 'queued' | 'running' | 'completed' | 'failed' | 'skipped' | 'error' | string
  action_type: string
  created_at: string | null
  started_at: string | null
  completed_at: string | null
  output: unknown
  error: string | null
}
