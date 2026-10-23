import type { Automation } from '../../types/automation'
import { describeSchedule, toScheduleConfig } from '../../utils/schedule'

export interface AutomationFolderNames { folders: { uuid: string; path: string }[]; loading: boolean; error: string | null }

export function describeAutomation(automation: Automation, names: AutomationFolderNames, actionName?: string) {
  const config = automation.trigger_config || {}
  const folder = (id: unknown) => typeof id !== 'string' || !id ? 'Choose a folder' : names.folders.find(item => item.uuid === id)?.path ?? (names.loading ? 'Loading folder name…' : 'Folder name unavailable')
  let trigger = 'Trigger not recognized'
  let input = 'Review trigger settings'
  if (automation.trigger_type === 'folder_watch') {
    trigger = 'When files arrive'
    input = folder(config.folder_id)
    if (Array.isArray(config.file_types) && config.file_types.length) input += ` · ${config.file_types.join(', ')}`
  } else if (automation.trigger_type === 'schedule') {
    trigger = config.frequency && config.time && config.timezone ? describeSchedule(toScheduleConfig(config)) : 'Schedule needs configuration'
    if (config.source === 'folder') input = folder(config.folder_id)
    else {
      const count = Array.isArray(config.document_uuids) ? config.document_uuids.length : 0
      input = count ? `${count} selected document${count === 1 ? '' : 's'}` : 'Choose input documents'
    }
    if (config.only_new) input += ' · new files only'
  } else if (automation.trigger_type === 'api') {
    trigger = 'On an API request'; input = 'Documents or text provided by the caller'
  } else if (automation.trigger_type === 'm365_intake') {
    trigger = 'On Microsoft 365 intake'; input = 'Files from the configured Microsoft 365 source'
  }
  const kind = automation.action_type === 'extraction' ? 'Extraction' : automation.action_type === 'task' ? 'Task' : 'Workflow'
  const action = automation.action_id ? `${kind}: ${automation.action_name || actionName || 'Name unavailable'}` : `Choose a ${kind.toLowerCase()}`
  const outputConfig = automation.output_config || {}
  const storage = outputConfig.storage as { enabled?: boolean; destination_folder?: string; format?: string } | undefined
  const deliveries: string[] = []
  if (storage?.enabled) deliveries.push(`${(storage.format || (automation.action_type === 'extraction' ? 'csv' : 'text')).toUpperCase()} → ${folder(storage.destination_folder)}`)
  if (Array.isArray(outputConfig.notifications) && outputConfig.notifications.length) deliveries.push('Notifications configured')
  if (Array.isArray(outputConfig.webhooks) && outputConfig.webhooks.length) deliveries.push(`${outputConfig.webhooks.length} webhook${outputConfig.webhooks.length === 1 ? '' : 's'}`)
  if (Array.isArray(outputConfig.chains) && outputConfig.chains.length) deliveries.push(`${outputConfig.chains.length} follow-up automation${outputConfig.chains.length === 1 ? '' : 's'}`)
  if ((outputConfig.onedrive as { enabled?: boolean } | undefined)?.enabled) deliveries.push('OneDrive delivery')
  const output = deliveries.length ? deliveries.join(' · ') : 'Recorded output in run history'
  return { trigger, input, action, output }
}

export function AutomationSummary({ automation, names, actionName, compact = false }: { automation: Automation; names: AutomationFolderNames; actionName?: string; compact?: boolean }) {
  const summary = describeAutomation(automation, names, actionName)
  return <dl className={`automation-summary${compact ? ' automation-summary-compact' : ''}`} aria-label="Automation summary">
    {Object.entries(summary).map(([label, value]) => <div key={label}><dt>{label === 'input' ? 'Input' : label === 'output' ? 'Output' : label === 'action' ? 'Action' : 'Trigger'}</dt><dd>{value}</dd></div>)}
  </dl>
}
