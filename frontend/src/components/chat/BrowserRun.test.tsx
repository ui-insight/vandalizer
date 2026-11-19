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
  expect(screen.getAllByText(/could change something on the site/)[0]).toBeVisible()
  // The tool's own message is written for the model.
  expect(screen.queryByText(/Submit Invoice would change something/)).not.toBeInTheDocument()
})

const step = (id: string, tool_name: string, args: Record<string, unknown>, content: Record<string, unknown>) => ({ call: { tool_call_id: id, tool_name, args }, content })
function run(steps: ReturnType<typeof step>[]) {
  const map = new Map<string, ToolResultInfo>(steps.map(({ call, content }) => [call.tool_call_id, { ...call, content, quality: null }]))
  return render(<BrowserRun calls={steps.map(s => s.call)} results={map} />)
}
const NOT_ON_PAGE = { recorded: false, error: 'value_not_on_page', message: "'Thinking big' does not appear on any page read this turn. Read the page again and copy the value exactly, or say that you could not find it." }
const NEEDS_APPROVAL = { error: 'browser_needs_approval', message: "This needs the person's approval before the browser is used. Call browser_open with the site's address; they will be shown an approval card." }
const PAGE = { page: { url: 'https://www.uidaho.edu/search', title: 'Search' } }
const recorded = (label: string, value: string) => ({ recorded: true, label, value, url: 'https://www.uidaho.edu/search', page_title: 'Search' })

it('drops a not-found warning once the same value is recorded', () => {
  run([
    step('open', 'browser_open', {}, PAGE),
    step('miss', 'record_value', { label: 'Result 1', value: 'Thinking big for Idaho\'s future' }, NOT_ON_PAGE),
    // Second try: same title with the page's curly apostrophe.
    step('hit', 'record_value', { label: 'First result', value: 'Thinking big for Idaho’s future' }, recorded('First result', 'Thinking big for Idaho’s future')),
  ])
  expect(screen.getByText('1 figure recorded')).toBeInTheDocument()
  expect(screen.queryByText('Step needs attention.')).not.toBeInTheDocument()
})
it('drops a not-found warning once that figure is recorded with a corrected value', () => {
  run([
    step('open', 'browser_open', {}, PAGE),
    step('miss', 'record_value', { label: 'Enrollment', value: '11,507 students' }, NOT_ON_PAGE),
    step('hit', 'record_value', { label: 'Enrollment', value: '11,507' }, recorded('Enrollment', '11,507')),
  ])
  expect(screen.queryByText('Step needs attention.')).not.toBeInTheDocument()
})
it('keeps a not-found warning for a value that was never recorded, in words for the person', () => {
  run([
    step('open', 'browser_open', {}, PAGE),
    step('miss', 'record_value', { label: 'Research spending', value: '$135 million' }, NOT_ON_PAGE),
    step('hit', 'record_value', { label: 'Enrollment', value: '11,507' }, recorded('Enrollment', '11,507')),
  ])
  expect(screen.getByText('Step needs attention.')).toBeVisible()
  expect(screen.getByText(/Chat could not find “\$135 million” on the pages it read, so it was not recorded\./)).toBeVisible()
  expect(screen.queryByText(/Read the page again|copy the value exactly/)).not.toBeInTheDocument()
})
it('drops an approval warning once a later browser step went through', () => {
  const { container } = run([
    step('read', 'browser_read', {}, NEEDS_APPROVAL),
    step('open', 'browser_open', { url: 'https://public.era.nih.gov/commons/' }, { login_required: true, page: { url: 'https://public.era.nih.gov/commons/', title: 'eRA Commons' } }),
  ])
  expect(screen.getByText('Sign in to continue')).toBeVisible()
  expect(screen.queryByText('Step needs attention.')).not.toBeInTheDocument()
  // Not in the activity log either.
  expect(container.textContent).not.toMatch(/browser_open|the person/)
})
it('never shows the tool message when the approval step is the last one', () => {
  const { container } = run([step('read', 'browser_read', {}, { ...NEEDS_APPROVAL, site: 'public.era.nih.gov' })])
  expect(screen.getAllByText(/Chat needs your approval before it uses the browser on public\.era\.nih\.gov/)[0]).toBeVisible()
  expect(container.textContent).not.toMatch(/browser_open|the person/)
})
it('keeps a warning when no later browser step went through', () => {
  run([
    step('read', 'browser_read', {}, { error: 'browser_timeout', message: 'The browser did not answer in time. The person may have closed the Vandalizer tab.' }),
    step('again', 'browser_read', {}, { error: 'no_open_page', message: 'No page is open yet. Use browser_open first.' }),
  ])
  expect(screen.getByText('Step needs attention.')).toBeVisible()
  expect(screen.getAllByText(/The browser did not answer in time\. Check that the working tab is still open/)[0]).toBeVisible()
  expect(screen.getAllByText('The working tab was closed. Ask chat to open the site again.')[0]).toBeVisible()
})
it('says a repeated problem once', () => {
  run([
    step('a', 'browser_click', { ref: 3 }, { error: 'stale_ref', message: 'No element [3] on the page now. Read the page again.' }),
    step('b', 'browser_click', { ref: 4 }, { error: 'stale_ref', message: 'No element [4] on the page now. Read the page again.' }),
    step('c', 'browser_read', {}, { error: 'browser_timeout' }),
  ])
  expect(screen.getAllByText('Step needs attention.')).toHaveLength(1)
})
it('gives an unknown error the general line, not its raw text', () => {
  const { container } = run([step('read', 'browser_read', {}, { error: 'something_new', message: 'Call browser_read with query set.' })])
  expect(screen.getAllByText('Chat could not read the page. Check the working tab before continuing.')[0]).toBeVisible()
  expect(container.textContent).not.toMatch(/browser_read|something_new/)
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
