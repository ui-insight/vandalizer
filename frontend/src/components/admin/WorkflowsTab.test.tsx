import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { WorkflowsTab } from './WorkflowsTab'
import { AdminViewState } from './shared/AdminViewState'
import { getWorkflowEvents } from '../../api/admin'
vi.mock('../../api/admin', () => ({ getWorkflowEvents: vi.fn() }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
it('retains linked date scope through section navigation and clears it deliberately', async () => {
  vi.mocked(getWorkflowEvents).mockResolvedValue({ items: [], total: 0, page: 1, pages: 1, summary: null })
  const from = '2026-01-01T00:00:00Z', until = '2026-01-08T00:00:00Z'
  const onFilterChange = vi.fn()
  const shell = (visible: boolean, linkedFilter?: { status?: string; from?: string; until?: string }) => <AdminViewState scope="workflow-window-test">{visible ? <WorkflowsTab linkedFilter={linkedFilter} onFilterChange={onFilterChange} /> : <p>Other section</p>}</AdminViewState>
  const view = render(shell(true, { status: 'failed', from, until }))
  await screen.findByText('No workflow events found.')
  expect(getWorkflowEvents).toHaveBeenLastCalledWith(1, 'failed', undefined, { from, until })
  view.rerender(shell(false))
  view.rerender(shell(true))
  await screen.findByText('No workflow events found.')
  expect(getWorkflowEvents).toHaveBeenLastCalledWith(1, 'failed', undefined, { from, until })
  fireEvent.click(screen.getByRole('button', { name: 'completed' }))
  expect(onFilterChange).toHaveBeenLastCalledWith({ status: 'completed', from, until })
  fireEvent.click(screen.getByRole('button', { name: 'Clear date range' }))
  await waitFor(() => expect(getWorkflowEvents).toHaveBeenLastCalledWith(1, 'completed', undefined, { from: undefined, until: undefined }))
  expect(screen.queryByText(/Workflow start window/)).not.toBeInTheDocument()
})
