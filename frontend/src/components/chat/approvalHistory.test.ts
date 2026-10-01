import { describe, expect, it } from 'vitest'
import { approvalHistoryFor } from './approvalHistory'
import type { ChatMessage } from '../../types/chat'
const preview: ChatMessage = { role: 'assistant', content: '', tool_calls: [{ tool_name: 'create_workflow', tool_call_id: 'preview', args: { name: 'Budget', confirmed: false } }], tool_results: [{ tool_name: 'create_workflow', tool_call_id: 'preview', content: { needs_confirmation: true }, quality: null }] }
const approval: ChatMessage = { role: 'user', content: 'Yes, go ahead' }
const executed: ChatMessage = { role: 'assistant', content: '', tool_calls: [{ tool_name: 'create_workflow', tool_call_id: 'run', args: { confirmed: true, name: 'Budget' } }], tool_results: [{ tool_name: 'create_workflow', tool_call_id: 'run', content: { workflow_id: 'wf-1' }, quality: null }] }
describe('historical approval evidence', () => {
  it('leaves the current preview actionable', () => expect(approvalHistoryFor(preview, [])).toEqual({}))
  it('records an accepted decision without claiming execution', () => expect(approvalHistoryFor(preview, [approval]).preview.label).toBe('Approval requested'))
  it('records cancellation on reload', () => expect(approvalHistoryFor(preview, [{ role: 'user', content: 'No, cancel that' }]).preview.label).toBe('Cancellation requested'))
  it('matches a result only for identical confirmed action arguments', () => expect(approvalHistoryFor(preview, [approval, executed]).preview.label).toBe('Workflow created'))
  it('does not attribute another item’s result to this preview', () => {
    const different = { ...executed, tool_calls: [{ ...executed.tool_calls![0], args: { name: 'Other', confirmed: true } }] }
    expect(approvalHistoryFor(preview, [approval, different]).preview.label).toBe('Approval requested')
  })
  it('does not consume an unrelated later turn', () => expect(approvalHistoryFor(preview, [approval, { role: 'user', content: 'Start a new task' }, executed]).preview.label).toBe('Approval requested'))
  it('uses failure evidence instead of the approval request', () => {
    const failed = { ...executed, tool_results: [{ ...executed.tool_results![0], content: { error: 'Permission denied' } }] }
    expect(approvalHistoryFor(preview, [approval, failed]).preview.label).toBe('Failed')
  })
})
