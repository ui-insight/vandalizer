import { describe, expect, it } from 'vitest'
import { approvalHistoryFor } from './approvalHistory'
import type { ChatMessage } from '../../types/chat'
const preview: ChatMessage = { role: 'assistant', content: '', tool_calls: [{ tool_name: 'create_workflow', tool_call_id: 'preview', args: { name: 'Budget', confirmed: false } }], tool_results: [{ tool_name: 'create_workflow', tool_call_id: 'preview', content: { needs_confirmation: true }, quality: null }] }
const approval: ChatMessage = { role: 'user', content: 'Yes, go ahead' }
const executed: ChatMessage = { role: 'assistant', content: '', tool_calls: [{ tool_name: 'create_workflow', tool_call_id: 'run', args: { confirmed: true, name: 'Budget' } }], tool_results: [{ tool_name: 'create_workflow', tool_call_id: 'run', content: { workflow_id: 'wf-1' }, quality: null }] }
const skill = { uuid: 'award', title: 'Award Review', instructions: 'When reviewing an award, add attribution.', version: 'v1' }
const skillPreview = (uuid: string | null): ChatMessage => ({ role: 'assistant', content: '',
  tool_calls: [{ tool_name: 'select_skill', tool_call_id: 'preview', args: { skill_uuid: uuid } }],
  tool_results: [{ tool_name: 'select_skill', tool_call_id: 'preview', content: { needs_confirmation: true }, quality: null }],
})
const skillReceipt = (selected: typeof skill | null): ChatMessage => ({ role: 'assistant', content: '',
  tool_results: [{ tool_name: 'select_skill', tool_call_id: 'changed', content: { status: 'selected', active_skill: selected }, quality: null }],
})
describe('historical approval evidence', () => {
  it('matches a saved page by its immutable preview ID without repeating large HTML arguments', () => {
    const id = 'a'.repeat(32)
    const page: ChatMessage = { role: 'assistant', content: '', tool_calls: [{ tool_name: 'revise_html_artifact', tool_call_id: 'page-preview', args: { html: '<table>All the rows</table>', base_revision: 'v1', title: 'NIH' } }], tool_results: [{ tool_name: 'revise_html_artifact', tool_call_id: 'page-preview', content: { needs_confirmation: true, preview_id: id }, quality: null }] }
    const saved: ChatMessage = { role: 'assistant', content: '', tool_calls: [{ tool_name: 'revise_html_artifact', tool_call_id: 'saved', args: { preview_id: id, confirmed: true } }], tool_results: [{ tool_name: 'revise_html_artifact', tool_call_id: 'saved', content: { artifact_uuid: 'page', revision: 'v2', preview_id: id }, quality: null }] }
    expect(approvalHistoryFor(page, [approval, saved])['page-preview'].label).toBe('Result recorded')
    const failed = { ...saved, tool_results: [{ ...saved.tool_results![0], content: { error: 'Temporary failure' } }] }
    expect(approvalHistoryFor(page, [approval, failed, saved])['page-preview'].label).toBe('Result recorded')
    expect(approvalHistoryFor(page, [approval])['page-preview'].label).toBe('Save not confirmed')
    const different = { ...saved, tool_calls: [{ ...saved.tool_calls![0], args: { preview_id: 'other', confirmed: true } }] }
    expect(approvalHistoryFor(page, [approval, different])['page-preview'].label).toBe('Approval requested')
  })
  it('leaves the current preview actionable', () => expect(approvalHistoryFor(preview, [])).toEqual({}))
  it('records an accepted decision without claiming execution while the turn runs', () => expect(approvalHistoryFor(preview, [approval], true).preview.label).toBe('Approval requested'))
  it('says nothing was done when the Assistant never answered the approval', () => {
    // Support ticket: tokens ran out after Create extraction; the card still read "Approval requested".
    const record = approvalHistoryFor(preview, [approval]).preview
    expect(record.label).toBe('Not done')
    expect(record.detail).toMatch(/couldn't respond.*nothing was created/)
  })
  it('says nothing was done when the reply never carried out the action', () => {
    const chatter: ChatMessage = { role: 'assistant', content: 'Sounds good! Anything else?' }
    expect(approvalHistoryFor(preview, [approval, chatter]).preview.label).toBe('Not done')
  })
  it('does not call an interrupted reply not done', () => {
    const stopped: ChatMessage = { role: 'assistant', content: 'Creating', interruption: 'connection' }
    expect(approvalHistoryFor(preview, [approval, stopped]).preview.label).toBe('Approval requested')
  })
  it('records cancellation on reload', () => expect(approvalHistoryFor(preview, [{ role: 'user', content: 'No, cancel that' }]).preview.label).toBe('Cancellation requested'))
  it('matches a result only for identical confirmed action arguments', () => expect(approvalHistoryFor(preview, [approval, executed]).preview.label).toBe('Workflow created'))
  it('does not attribute another item’s result to this preview', () => {
    const different = { ...executed, tool_calls: [{ ...executed.tool_calls![0], args: { name: 'Other', confirmed: true } }] }
    expect(approvalHistoryFor(preview, [approval, different]).preview.label).toBe('Approval requested')
  })
  it('does not consume an unrelated later turn', () => expect(approvalHistoryFor(preview, [approval, { role: 'user', content: 'Start a new task' }, executed]).preview.label).toBe('Not done'))
  it('uses failure evidence instead of the approval request', () => {
    const failed = { ...executed, tool_results: [{ ...executed.tool_results![0], content: { error: 'Permission denied' } }] }
    expect(approvalHistoryFor(preview, [approval, failed]).preview.label).toBe('Failed')
  })
  it.each([skill, null])('uses a successful Skill receipt even without the model call (%j)', selected => {
    const result = approvalHistoryFor(skillPreview(selected?.uuid ?? null), [approval, skillReceipt(selected)]).preview
    expect(result.label).toBe(selected ? 'Skill selected' : 'Skill removed')
    expect(result.detail).not.toContain('nothing was created or changed')
  })
  it('uses persisted segments and result targets without relying on confirmed arguments', () => {
    const receipt = skillReceipt(null)
    // The backend coerces boolean tool parameters, but the transcript retains
    // the model's raw arguments. The completed receipt is authoritative.
    receipt.tool_calls = [{ tool_name: 'select_skill', tool_call_id: 'changed', args: { skill_uuid: null, confirmed: 'true' } }]
    receipt.segments = [{ kind: 'tool_result', result: receipt.tool_results![0] }]
    delete receipt.tool_results
    const original = skillPreview(null)
    original.tool_results![0].content = { needs_confirmation: true, skill_uuid: null }
    delete original.tool_calls
    expect(approvalHistoryFor(original, [approval, receipt]).preview.label).toBe('Skill removed')
  })
  it('does not infer removal from missing, incomplete, or unrelated evidence', () => {
    const incomplete: ChatMessage = { role: 'assistant', content: 'Removed.', tool_results: [
      { tool_name: 'select_skill', tool_call_id: 'changed', content: { status: 'selected' }, quality: null },
    ] }
    for (const responses of [[], [incomplete], [skillReceipt(skill)], [{ role: 'user' as const, content: 'New task' }, skillReceipt(null)]]) {
      const record = approvalHistoryFor(skillPreview(null), [approval, ...responses]).preview
      expect(record.label).toBe('Change not confirmed')
      expect(record.detail).not.toContain('nothing was created or changed')
    }
    expect(approvalHistoryFor(skillPreview(skill.uuid), [approval, skillReceipt({ ...skill, uuid: 'other' })]).preview.label).toBe('Change not confirmed')
  })
  it('does not mark a failed or pending Skill change as successful', () => {
    for (const content of [{ error: 'Save failed', status: 'selected', active_skill: null }, { needs_confirmation: true, status: 'selected', active_skill: null }]) {
      const response = skillReceipt(null)
      response.tool_results![0].content = content
      expect(approvalHistoryFor(skillPreview(null), [approval, response]).preview.label).toBe('Change not confirmed')
    }
  })
})


describe('obligation approval receipts', () => {
  it.each([true, false])('matches the saved batch even when rejected inputs were omitted (same batch: %s)', same => {
    const original: ChatMessage = { role: 'assistant', content: '',
      tool_calls: [{ tool_name: 'propose_obligations', tool_call_id: 'batch', args: { obligations: ['accepted', 'rejected'] } }],
      tool_results: [{ tool_name: 'propose_obligations', tool_call_id: 'batch', quality: null, content: { needs_confirmation: true, approval_key: 'reviewed-batch' } }],
    }
    const receipt: ChatMessage = { role: 'assistant', content: '',
      tool_calls: [{ tool_name: 'propose_obligations', tool_call_id: 'saved', args: { obligations: ['accepted'], confirmed: true } }],
      tool_results: [{ tool_name: 'propose_obligations', tool_call_id: 'saved', quality: null, content: { ok: true, approval_key: same ? 'reviewed-batch' : 'another-batch', added: [{ title: 'Report' }] } }],
    }
    expect(approvalHistoryFor(original, [approval, receipt]).batch.label).toBe(same ? 'Added to inbox' : 'Approval requested')
  })
})
