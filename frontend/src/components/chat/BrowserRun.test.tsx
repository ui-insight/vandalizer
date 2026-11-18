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
it('omits malformed capture dates', () => { expect(capturedTime('not a date')).toBe('') })
