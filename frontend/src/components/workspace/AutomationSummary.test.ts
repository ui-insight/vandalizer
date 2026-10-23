import { describe, expect, it } from 'vitest'
import { describeAutomation } from './AutomationSummary'
import type { Automation } from '../../types/automation'
const base: Automation = { id: 'automation-1', name: 'Review', description: null, enabled: true, user_id: 'reviewer', team_id: null, shared_with_team: false, can_manage: true, created_at: '', updated_at: '', trigger_type: 'folder_watch', trigger_config: { folder_id: 'in', file_types: ['pdf'] }, action_type: 'workflow', action_id: 'w', action_name: 'Review proposal', output_config: {} }
const names = { folders: [{ uuid: 'in', path: 'Proposals / Incoming' }, { uuid: 'out', path: 'Proposals / Reviewed' }], loading: false, error: null }
describe('automation configuration summaries', () => {
  it('names the input, action and delivery without exposing webhook secrets', () => {
    const summary = describeAutomation({ ...base, output_config: { storage: { enabled: true, destination_folder: 'out', format: 'pdf' }, notifications: [{}], webhooks: [{ url: 'https://secret.example/token' }], chains: [{}] } }, names)
    expect(summary).toEqual({ trigger: 'When files arrive', input: 'Proposals / Incoming · pdf', action: 'Workflow: Review proposal', output: 'PDF → Proposals / Reviewed · Notifications configured · 1 webhook · 1 follow-up automation' })
    expect(JSON.stringify(summary)).not.toContain('secret.example')
  })
  it('does not invent a folder name or a selected action', () => {
    expect(describeAutomation({ ...base, action_id: null }, { folders: [], loading: true, error: null })).toMatchObject({ input: 'Loading folder name… · pdf', action: 'Choose a workflow' })
    expect(describeAutomation(base, { folders: [], loading: false, error: 'Offline' }).input).toBe('Folder name unavailable · pdf')
    expect(describeAutomation({ ...base, trigger_config: {} }, names).input).toBe('Choose a folder')
  })
  it('describes scheduled documents and missing schedule configuration honestly', () => {
    const scheduled = { ...base, trigger_type: 'schedule' as const, trigger_config: { frequency: 'daily', time: '09:00', timezone: 'America/Los_Angeles', source: 'documents', document_uuids: ['a', 'b'], only_new: true } }
    expect(describeAutomation(scheduled, names)).toMatchObject({ input: '2 selected documents · new files only', output: 'Recorded output in run history' })
    expect(describeAutomation(scheduled, names).trigger).toContain('09:00')
    expect(describeAutomation({ ...scheduled, trigger_config: {} }, names)).toMatchObject({ trigger: 'Schedule needs configuration', input: 'Choose input documents' })
  })
  it('covers API and Microsoft 365 inputs, extraction outputs and fallback action names', () => {
    expect(describeAutomation({ ...base, trigger_type: 'api', action_type: 'extraction', action_name: null, output_config: { storage: { enabled: true, destination_folder: 'out' } } }, names, 'Award fields')).toMatchObject({ input: 'Documents or text provided by the caller', action: 'Extraction: Award fields', output: 'CSV → Proposals / Reviewed' })
    expect(describeAutomation({ ...base, trigger_type: 'm365_intake' }, names)).toMatchObject({ trigger: 'On Microsoft 365 intake', input: 'Files from the configured Microsoft 365 source' })
  })
})
