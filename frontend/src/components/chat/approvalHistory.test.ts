import { describe, expect, it } from 'vitest'
import { approvalHistoryFor } from './approvalHistory'
import type { ChatMessage } from '../../types/chat'
const preview: ChatMessage = { role: 'assistant', content: '', tool_calls: [{ tool_name: 'create_workflow', tool_call_id: 'preview', args: { name: 'Budget', confirmed: false } }], tool_results: [{ tool_name: 'create_workflow', tool_call_id: 'preview', content: { needs_confirmation: true }, quality: null }] }
const approval: ChatMessage = { role: 'user', content: 'Yes, go ahead' }
const executed: ChatMessage = { role: 'assistant', content: '', tool_calls: [{ tool_name: 'create_workflow', tool_call_id: 'run', args: { confirmed: true, name: 'Budget' } }], tool_results: [{ tool_name: 'create_workflow', tool_call_id: 'run', content: { workflow_id: 'wf-1' }, quality: null }] }
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
})
