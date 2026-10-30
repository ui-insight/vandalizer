import { expect, it } from 'vitest'
import type { ChatMessage, ToolResultInfo } from '../types/chat'
import { hasPendingPageApproval } from './pageApprovals'

const result = (content: unknown, tool_call_id = 'preview'): ToolResultInfo => ({ tool_name: 'revise_html_artifact', tool_call_id, content, quality: null })
const preview: ChatMessage = { role: 'assistant', content: 'Click Save new version.', segments: [
  { kind: 'tool_result', result: result({ needs_confirmation: true, preview_id: 'footer' }) },
] }
const approve: ChatMessage = { role: 'user', content: 'Yes, go ahead' }
const receipt = (content: unknown): ChatMessage => ({ role: 'assistant', content: '', tool_results: [result(content, 'save')] })

it('reconstructs a pending preview from saved transcript segments', () => {
  expect(hasPendingPageApproval([preview])).toBe(true)
  expect(hasPendingPageApproval([preview, approve])).toBe(true)
})

it('requires a successful receipt for the same immutable preview', () => {
  const saved = { artifact_uuid: 'page', revision: 'revision', preview_id: 'footer' }
  expect(hasPendingPageApproval([preview, approve, receipt(saved)])).toBe(false)
  expect(hasPendingPageApproval([preview, approve, receipt({ ...saved, preview_id: 'another' })])).toBe(true)
  expect(hasPendingPageApproval([preview, approve, receipt({ ...saved, error: 'Failed' })])).toBe(true)
  expect(hasPendingPageApproval([preview, approve, receipt({ artifact_uuid: 'page', revision: 'revision' })])).toBe(true)
})

it('uses a saved call preview ID when the result omits it', () => {
  const saved = receipt({ artifact_uuid: 'page', revision: 'revision' })
  saved.segments = [{ kind: 'tool_call', call: { tool_name: 'revise_html_artifact', tool_call_id: 'save', args: { preview_id: 'footer', confirmed: true } } }]
  expect(hasPendingPageApproval([preview, approve, saved])).toBe(false)
})

it('releases an explicitly cancelled preview', () => {
  expect(hasPendingPageApproval([preview, { role: 'user', content: 'No, cancel that' }])).toBe(false)
})

it('does not block a reopened legacy conversation on an already historical preview', () => {
  expect(hasPendingPageApproval([preview, { role: 'user', content: 'An unrelated question' }, { role: 'assistant', content: 'Answer' }])).toBe(false)
})

it('does not hold the Page queue for other kinds of approvals', () => {
  const other = receipt({ needs_confirmation: true })
  other.tool_results![0].tool_name = 'create_project'
  expect(hasPendingPageApproval([other])).toBe(false)
})
