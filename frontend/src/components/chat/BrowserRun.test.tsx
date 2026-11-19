import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { BrowserRun, capturedTime } from './BrowserRun'
import { groupBrowserSegments } from './browserToolGroups'
import type { ToolCallInfo, ToolResultInfo } from '../../types/chat'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ sendChatMessage: vi.fn() }) }))
afterEach(cleanup)
const calls: ToolCallInfo[] = [
  { tool_call_id: 'open', tool_name: 'browser_open', args: { url: 'https://example.edu' } },
  { tool_call_id: 'figure', tool_name: 'record_value', args: {} },
]
const results = new Map<string, ToolResultInfo>([
  ['open', { ...calls[0], content: { page: { url: 'https://example.edu/awards', title: 'Awards' } }, quality: null }],
  ['figure', { ...calls[1], content: { recorded: true, label: 'Award balance', value: '$42,000', url: 'https://example.edu/awards', page_title: 'Awards', captured_at: '2026-11-17T19:35:16+00:00' }, quality: null }],
])
it('keeps source evidence accessible in a compact group with readable capture times', () => {
  render(<BrowserRun calls={calls} results={results} />)
  expect(screen.getAllByText('Read-only browser')).toHaveLength(1)
  expect(screen.getByText('$42,000')).not.toBeVisible()
  fireEvent.click(screen.getByText('1 figure recorded'))
  expect(screen.getByText('$42,000')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Awards' })).toHaveAttribute('href', 'https://example.edu/awards')
  expect(screen.getByText(/Captured/)).not.toHaveTextContent('T19:35:16')
})
it('preserves refusals even when later steps succeed', () => {
  const blocked = { tool_call_id: 'blocked', tool_name: 'browser_click', args: {} }
  const map = new Map(results)
  map.set(blocked.tool_call_id, { ...blocked, content: { error: 'blocked_write_action', message: 'Submit Invoice would change something.' }, quality: null })
  render(<BrowserRun calls={[blocked, ...calls]} results={map} />)
  expect(screen.getByText('Action blocked.')).toBeVisible()
  expect(screen.getAllByText(/Submit Invoice would change something/)[0]).toBeVisible()
})
it('does not render untrusted source URL schemes as links', () => {
  const map = new Map(results)
  map.set('figure', { ...results.get('figure')!, content: { recorded: true, label: 'Balance', value: '42', url: 'javascript:alert(1)' } })
  render(<BrowserRun calls={[calls[1]]} results={map} />)
  expect(screen.queryByRole('link')).not.toBeInTheDocument()
  expect(screen.getByText('Source unavailable')).toBeVisible()
})
it('groups browser work without moving narrative or other tools', () => {
  const text = { kind: 'text' as const, content: 'Now compare these figures.' }
  const groups = groupBrowserSegments([
    { kind: 'tool_call', call: calls[0] },
    { kind: 'tool_result', result: results.get('open')! },
    { kind: 'tool_call', call: calls[1] },
    text,
    { kind: 'tool_call', call: { tool_call_id: 'calc', tool_name: 'calculate', args: {} } },
    { kind: 'tool_call', call: calls[0] },
  ])
  expect(groups.map(group => group.kind)).toEqual(['browser_group', 'text', 'tool_call', 'browser_group'])
  expect(groups[0]).toEqual({ kind: 'browser_group', calls })
  expect(groups[1]).toBe(text)
})
it('leaves a browser call that is waiting for approval out of the group, so it gets an approval card', () => {
  const waiting = { tool_call_id: 'ask', tool_name: 'browser_open', args: { url: 'https://portal.example.edu' } }
  const map = new Map(results)
  map.set('ask', { ...waiting, content: { needs_confirmation: true, approval_label: 'Open site' }, quality: null })
  const groups = groupBrowserSegments([
    { kind: 'tool_call', call: calls[0] },
    { kind: 'tool_call', call: waiting },
    { kind: 'tool_result', result: map.get('ask')! },
    { kind: 'tool_call', call: calls[1] },
  ], map)
  expect(groups).toEqual([{ kind: 'browser_group', calls: [calls[0]] }, { kind: 'tool_call', call: waiting }, { kind: 'browser_group', calls: [calls[1]] }])
})
it('never logs a step that is waiting for approval as completed', () => {
  const waiting = { tool_call_id: 'ask', tool_name: 'browser_open', args: {} }
  render(<BrowserRun calls={[waiting]} results={new Map([['ask', { ...waiting, content: { needs_confirmation: true }, quality: null }]])} />)
  expect(screen.getByText('Waiting for your approval')).toBeInTheDocument()
  expect(screen.queryByText('Browser step completed')).not.toBeInTheDocument()
})
it('omits malformed capture dates', () => { expect(capturedTime('not a date')).toBe('') })
