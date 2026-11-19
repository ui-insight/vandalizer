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
it('keeps a warning when the only later step is a site waiting for approval, which opened nothing', () => {
  run([
    step('read', 'browser_read', {}, { error: 'browser_timeout' }),
    step('ask', 'browser_open', { url: 'https://portal.example.edu' }, { needs_confirmation: true, status: 'awaiting_user_confirmation', site: 'portal.example.edu' }),
    step('again', 'browser_open', { url: 'https://portal.example.edu' }, { still_waiting: true, status: 'awaiting_user_confirmation' }),
  ])
  expect(screen.getByText('Step needs attention.')).toBeVisible()
  expect(screen.getAllByText(/The browser did not answer in time/)[0]).toBeVisible()
})
it('keeps a warning about one site when a different site is read afterwards', () => {
  run([
    step('a', 'browser_open', { url: 'https://finance.example.edu/awards' }, { error: 'browser_timeout' }),
    step('b', 'browser_open', { url: 'https://www.uidaho.edu/search' }, PAGE),
  ])
  expect(screen.getByText('Step needs attention.')).toBeVisible()
})
it('drops a warning about a site once a page on that site is read', () => {
  run([
    step('a', 'browser_open', { url: 'https://www.uidaho.edu/about' }, { error: 'browser_timeout' }),
    step('b', 'browser_open', { url: 'https://www.uidaho.edu/search' }, PAGE),
  ])
  expect(screen.queryByText('Step needs attention.')).not.toBeInTheDocument()
})
it('names each blocked control, so two of them are two notices', () => {
  run([
    step('a', 'browser_click', { ref: 3 }, { error: 'blocked_write_action', label: 'Submit Invoice', message: 'Submit Invoice would change something.' }),
    step('b', 'browser_click', { ref: 4 }, { error: 'blocked_write_action', label: 'Delete award', message: 'Delete award would change something.' }),
    step('c', 'browser_read', {}, PAGE),
  ])
  expect(screen.getAllByText('Action blocked.')).toHaveLength(2)
  expect(screen.getAllByText(/“Submit Invoice” could change something on the site/)[0]).toBeVisible()
  expect(screen.getAllByText(/“Delete award” could change something on the site/)[0]).toBeVisible()
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
it('words a refusal to open Vandalizer itself for the person, and keeps it', () => {
  const { container } = run([
    step('own', 'browser_open', {}, { error: 'vandalizer_itself', site: 'vandalizer.example.edu', message: 'x', hint: 'Tell the person plainly. Do not ask for approval.' }),
    step('open', 'browser_open', {}, PAGE),
  ])
  expect(screen.getByText('Action blocked.')).toBeVisible()
  expect(screen.getAllByText(/Chat’s browser can’t be used on Vandalizer itself/)[0]).toBeVisible()
  expect(container.textContent).not.toMatch(/Do not ask for approval/)
})
