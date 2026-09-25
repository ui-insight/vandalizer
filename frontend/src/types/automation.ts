export type TriggerType = 'folder_watch' | 'm365_intake' | 'api' | 'schedule'
export type ActionType = 'workflow' | 'extraction' | 'task'

export type ScheduleFrequency = 'daily' | 'weekly' | 'monthly'

/** trigger_config of a schedule automation — see backend automation_schedule.py. */
export interface ScheduleTriggerConfig {
  frequency: ScheduleFrequency
  /** "HH:MM", 24-hour, in `timezone`. */
  time: string
  /** 0 = Monday … 6 = Sunday (weekly). */
  weekday?: number
  /** 1 … 28 (monthly). */
  day_of_month?: number
  /** IANA zone, e.g. "America/Boise". */
  timezone: string
  source: 'folder' | 'documents'
  folder_id?: string
  document_uuids?: string[]
  /** Display names for document_uuids; the backend ignores it. */
  document_titles?: Record<string, string>
  /** After the first run, take only documents added since the previous run. */
  only_new?: boolean
  /** Derived by the backend from the fields above. */
  cron_expression?: string
}

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
  /** Schedule triggers: next and last firing, ISO UTC. */
  next_run_at?: string | null
  last_run_at?: string | null
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
