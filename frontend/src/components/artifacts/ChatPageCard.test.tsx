import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ToolStatusLine } from '../chat/ToolCallDisplay'
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({}) }))
const call = { tool_name: 'create_html_artifact', tool_call_id: 'preview', args: { title: 'Award report' } }
const result = { tool_name: call.tool_name, tool_call_id: call.tool_call_id, content: { needs_confirmation: true, artifact_preview_html: '<h1>Review this page</h1>' }, quality: null }
it('sends the stored revision preview ID when Save new version is clicked', () => {
  const confirm = vi.fn()
  const previewId = 'b'.repeat(32)
  const toolName = 'revise_html_artifact'
  render(<ToolStatusLine call={{ ...call, tool_name: toolName, args: { title: 'NIH dashboard', html: '<table>large content</table>' } }}
    result={{ ...result, tool_name: toolName, content: { ...result.content, preview_id: previewId } }} onConfirm={confirm} />)
  fireEvent.click(screen.getByRole('button', { name: 'Save new version' }))
  expect(confirm).toHaveBeenCalledExactlyOnceWith('Yes, go ahead', previewId)
  expect(screen.queryByRole('button', { name: 'Save new version' })).not.toBeInTheDocument()
})
it('lets a user inspect an isolated preview and approve exactly once', () => {
  const confirm = vi.fn()
  render(<ToolStatusLine call={call} result={result} onConfirm={confirm} />)
  expect(screen.getByTitle('Page preview')).toHaveAttribute('sandbox', 'allow-popups allow-popups-to-escape-sandbox')
  fireEvent.click(screen.getByRole('button', { name: 'Expand preview' }))
  const dialog = screen.getByRole('dialog', { name: 'Award report' })
  expect(screen.getByTitle('Award report expanded preview')).toHaveAttribute('sandbox', 'allow-popups allow-popups-to-escape-sandbox')
  fireEvent.keyDown(dialog, { key: 'Escape' })
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Save page' }))
  expect(confirm).toHaveBeenCalledWith('Yes, go ahead')
  expect(confirm).toHaveBeenCalledTimes(1)
  expect(screen.queryByRole('button', { name: 'Save page' })).not.toBeInTheDocument()
  expect(screen.getByText('Approval sent. Waiting for the saved page…')).toBeInTheDocument()
})
it('downloads the saved page revision separately from transcript exports', () => {
  const uuid = 'a'.repeat(32)
  render(<ToolStatusLine call={call} result={{ ...result, content: { artifact_uuid: uuid, title: 'Award report', revision: 'saved-version' } }} />)
  expect(screen.getByRole('link', { name: 'Download HTML: Award report' })).toHaveAttribute('href', `/api/pages/${uuid}/revisions/saved-version/content?download=true`)
  expect(screen.getByRole('link', { name: 'Share: Award report' })).toHaveAttribute('href', `/pages/${uuid}#share`)
  expect(screen.getByTitle('Page preview')).toHaveAttribute('src', `/api/pages/${uuid}/revisions/saved-version/content`)
})
it('never offers another approval for a historical decision', () => {
  render(<ToolStatusLine call={call} result={result} onConfirm={vi.fn()} approvalHistory={{ label: 'Result recorded', detail: 'Saved below.' }} />)
  expect(screen.queryByRole('button', { name: 'Save page' })).not.toBeInTheDocument()
  expect(screen.getByRole('region', { name: 'Earlier action decision' })).toHaveTextContent('Saved below.')
})
it('distinguishes preparing a preview from saving an approved page while the tool runs', () => {
  const { rerender } = render(<ToolStatusLine call={call} isActive />)
  expect(screen.getByRole('status')).toHaveTextContent('Preparing your page preview')
  rerender(<ToolStatusLine call={{ ...call, args: { ...call.args, confirmed: true } }} isActive />)
  expect(screen.getByRole('status')).toHaveTextContent('Saving your page')
  expect(screen.queryByText('Preparing a preview for you to review before saving.')).not.toBeInTheDocument()
})

it.each(['create_html_artifact', 'revise_html_artifact'])('shows removal warnings before saving a %s preview', toolName => {
  const warning = 'Scripts were removed. Data rendered only by scripts will be missing.'
  render(<ToolStatusLine call={{ ...call, tool_name: toolName }} result={{ ...result, tool_name: toolName, content: { ...result.content, warnings: [warning] } }} onConfirm={vi.fn()} />)
  const alert = screen.getByRole('alert')
  expect(alert).toHaveTextContent('Some content was removed to keep this page safe.')
  expect(alert).toHaveTextContent(warning)
  expect(alert.compareDocumentPosition(screen.getByTitle('Page preview')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(screen.getByText(/JavaScript charts, filters and table sorting are not supported/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: toolName === 'create_html_artifact' ? 'Save page' : 'Save new version' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Expand preview' }))
  expect(screen.getByRole('alert')).toHaveTextContent(warning)
  expect(screen.getByTitle('Award report expanded preview')).toHaveAttribute('sandbox', 'allow-popups allow-popups-to-escape-sandbox')
})

it('keeps warnings visible in saved and historical chat cards', () => {
  const warning = 'Unsupported scripts were removed.'
  const { rerender } = render(<ToolStatusLine call={call} result={{ ...result, content: { artifact_uuid: 'a'.repeat(32), revision: 'saved-version', warnings: [warning] } }} />)
  expect(screen.getByRole('alert')).toHaveTextContent(warning)
  rerender(<ToolStatusLine call={call} result={{ ...result, content: { ...result.content, warnings: [warning] } }} approvalHistory={{ label: 'Result recorded', detail: 'Saved below.' }} />)
  expect(screen.getByRole('alert')).toHaveTextContent(warning)
  expect(screen.queryByRole('button', { name: 'Save page' })).not.toBeInTheDocument()
})

it('handles legacy results and malformed warnings without inventing removals', () => {
  const { rerender } = render(<ToolStatusLine call={call} result={result} />)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.getByText(/Pages support jump links, expandable sections, and web or email links/)).toBeInTheDocument()
  rerender(<ToolStatusLine call={call} result={{ ...result, content: { ...result.content, warnings: [null, { message: 'invalid' }, 42] } }} />)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})


it('keeps jump links inside the unsaved and expanded preview', () => {
  const html = '<a href="#chart">Budget chart</a><h2 id="chart">Budget chart</h2><details><summary>Source notes</summary>Notes</details>'
  render(<ToolStatusLine call={call} result={{ ...result, content: { ...result.content, artifact_preview_html: html } }} onConfirm={vi.fn()} />)
  const frame = screen.getByTitle('Page preview')
  const preview = new DOMParser().parseFromString(frame.getAttribute('srcdoc')!, 'text/html')
  expect(preview.querySelector('a')?.getAttribute('href')).toBe('about:srcdoc#chart')
  expect(preview.getElementById('chart')).not.toBeNull()
  expect(preview.querySelector('details summary')?.textContent).toBe('Source notes')
  fireEvent.click(screen.getByRole('button', { name: 'Expand preview' }))
  expect(screen.getByTitle('Award report expanded preview')).toHaveAttribute('srcdoc', frame.getAttribute('srcdoc'))
  expect(frame.getAttribute('sandbox')).not.toMatch(/allow-scripts|allow-same-origin|allow-top-navigation(?: |$)/)
})
