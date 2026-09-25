import type { ScheduleTriggerConfig } from '../types/automation'

/** Monday-first, matching the backend's 0 = Monday. */
export const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

/** Every IANA zone the browser knows, with the viewer's own and UTC first. */
export function timeZoneOptions(): string[] {
  const own = browserTimeZone()
  let all: string[] = []
  try {
    all = Intl.supportedValuesOf('timeZone')
  } catch {
    all = []
  }
  return [...new Set([own, 'UTC', ...all])]
}

export function defaultScheduleConfig(): ScheduleTriggerConfig {
  return {
    frequency: 'weekly',
    weekday: 0,
    day_of_month: 1,
    time: '09:00',
    timezone: browserTimeZone(),
    source: 'folder',
    only_new: false,
  }
}

/** Read a stored trigger_config as a schedule, filling gaps with defaults. */
export function toScheduleConfig(raw: Record<string, unknown> | null | undefined): ScheduleTriggerConfig {
  return { ...defaultScheduleConfig(), ...(raw as Partial<ScheduleTriggerConfig> | undefined) }
}

/** Ready to save: the schedule names something to run on. */
export function isScheduleComplete(cfg: ScheduleTriggerConfig): boolean {
  if (!/^\d{2}:\d{2}$/.test(cfg.time)) return false
  return cfg.source === 'folder' ? !!cfg.folder_id : (cfg.document_uuids?.length ?? 0) > 0
}

/** The config as sent to the API: only the fields for the chosen source. */
export function scheduleConfigPayload(cfg: ScheduleTriggerConfig): Record<string, unknown> {
  const out: Record<string, unknown> = {
    frequency: cfg.frequency,
    time: cfg.time,
    timezone: cfg.timezone,
    source: cfg.source,
  }
  if (cfg.frequency === 'weekly') out.weekday = cfg.weekday ?? 0
  if (cfg.frequency === 'monthly') out.day_of_month = cfg.day_of_month ?? 1
  if (cfg.source === 'folder') {
    if (cfg.folder_id) out.folder_id = cfg.folder_id
    out.only_new = !!cfg.only_new
  } else {
    out.document_uuids = cfg.document_uuids ?? []
    out.document_titles = cfg.document_titles ?? {}
  }
  return out
}

function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`
}

/** "Every Monday at 09:00", "Daily at 17:30", "Monthly on the 1st at 08:00". */
export function describeSchedule(cfg: ScheduleTriggerConfig): string {
  if (cfg.frequency === 'daily') return `Daily at ${cfg.time}`
  if (cfg.frequency === 'weekly') return `Every ${WEEKDAYS[cfg.weekday ?? 0]} at ${cfg.time}`
  return `Monthly on the ${ordinal(cfg.day_of_month ?? 1)} at ${cfg.time}`
}

/** "Mon, Sep 28, 9:00 AM MDT" in the given zone. */
export function formatRunTime(iso: string, timeZone: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      weekday: 'short', month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit', timeZone, timeZoneName: 'short',
    }).format(new Date(iso))
  } catch {
    return new Date(iso).toLocaleString()
  }
}
