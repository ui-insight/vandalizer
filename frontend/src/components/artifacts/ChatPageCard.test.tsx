import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ToolStatusLine } from '../chat/ToolCallDisplay'
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({}) }))
const call = { tool_name: 'create_html_artifact', tool_call_id: 'preview', args: { title: 'Award report' } }
const result = { tool_name: call.tool_name, tool_call_id: call.tool_call_id, content: { needs_confirmation: true, artifact_preview_html: '<h1>Review this page</h1>' }, quality: null }
it('lets a user inspect an isolated preview and approve exactly once', () => {
  const confirm = vi.fn()
  render(<ToolStatusLine call={call} result={result} onConfirm={confirm} />)
  expect(screen.getByTitle('Page preview')).toHaveAttribute('sandbox', '')
  fireEvent.click(screen.getByRole('button', { name: 'Expand preview' }))
  const dialog = screen.getByRole('dialog', { name: 'Award report' })
  expect(screen.getByTitle('Award report expanded preview')).toHaveAttribute('sandbox', '')
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
