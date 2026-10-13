import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WorkflowVersionsTab } from './WorkflowVersionsTab'

const api = vi.hoisted(() => ({ list: vi.fn(), save: vi.fn(), restore: vi.fn(), confirm: vi.fn() }))
vi.mock('../../api/workflows', () => ({
  listWorkflowVersions: api.list, saveWorkflowVersion: api.save, restoreWorkflowVersion: api.restore,
}))
vi.mock('../shared/useConfirm', () => ({ useConfirm: () => api.confirm }))

const version = (number: number, extra: Record<string, unknown> = {}) => ({
  id: `v${number}`, number, note: `Note ${number}`, source: 'chat', created_by_user_id: 'u1', created_by_name: 'Jordan',
  created_at: '2026-10-13T12:00:00Z', restored_from: null, name: 'Scan', step_names: ['Extract', 'Check'], is_current: false, ...extra,
})

describe('workflow versions tab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.list.mockResolvedValue({
      versions: [version(2, { note: 'Check USDA rules instead of NSF', is_current: true }), version(1, { note: 'Original', source: 'original' })],
      unsaved_changes: false, can_manage: true,
    })
  })

  it('lists versions with their notes and marks the current one', async () => {
    render(<WorkflowVersionsTab workflowId="wf-1" onRestored={vi.fn()} />)
    const list = await screen.findByRole('list', { name: 'Workflow versions' })
    expect(list).toHaveTextContent('Version 2')
    expect(screen.getByText('Check USDA rules instead of NSF')).toBeInTheDocument()
    expect(screen.getByText('Current')).toBeInTheDocument()
    // The current version can't be restored; the earlier one can.
    expect(screen.queryByRole('button', { name: 'Restore version 2' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Restore version 1' })).toBeInTheDocument()
  })

  it('restores an earlier version after confirmation and reloads the editor', async () => {
    api.confirm.mockResolvedValue(true)
    api.restore.mockResolvedValue({ id: 'v3', number: 3, restored_from: 1, name_note: null })
    const onRestored = vi.fn()
    render(<WorkflowVersionsTab workflowId="wf-1" onRestored={onRestored} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Restore version 1' }))
    await waitFor(() => expect(api.restore).toHaveBeenCalledWith('wf-1', 'v1'))
    expect(onRestored).toHaveBeenCalledOnce()
    expect(await screen.findByText('Restored version 1 as version 3.')).toBeInTheDocument()
  })

  it('does nothing when the restore is canceled', async () => {
    api.confirm.mockResolvedValue(false)
    render(<WorkflowVersionsTab workflowId="wf-1" onRestored={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Restore version 1' }))
    await waitFor(() => expect(api.confirm).toHaveBeenCalled())
    expect(api.restore).not.toHaveBeenCalled()
  })

  it('offers to save editor changes as a version with a note', async () => {
    api.list.mockResolvedValueOnce({ versions: [version(1, { source: 'original' })], unsaved_changes: true, can_manage: true })
    api.save.mockResolvedValue({ id: 'v2', number: 2 })
    render(<WorkflowVersionsTab workflowId="wf-1" onRestored={vi.fn()} />)
    fireEvent.change(await screen.findByLabelText('What changed (optional)'), { target: { value: 'Tightened the prompt' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save version' }))
    await waitFor(() => expect(api.save).toHaveBeenCalledWith('wf-1', 'Tightened the prompt'))
    expect(await screen.findByText('Saved as version 2.')).toBeInTheDocument()
  })

  it('shows viewers the history without restore or save', async () => {
    api.list.mockResolvedValueOnce({ versions: [version(2, { is_current: true }), version(1)], unsaved_changes: true, can_manage: false })
    render(<WorkflowVersionsTab workflowId="wf-1" onRestored={vi.fn()} />)
    await screen.findByRole('list', { name: 'Workflow versions' })
    expect(screen.queryByRole('button', { name: /Restore/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save version' })).not.toBeInTheDocument()
  })
})
