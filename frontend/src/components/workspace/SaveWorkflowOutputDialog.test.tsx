import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { SaveWorkflowOutputDialog } from './SaveWorkflowOutputDialog'
import { listAllFolders } from '../../api/folders'
import { saveResultToFolder } from '../../api/workflows'
vi.mock('focus-trap-react', () => ({ FocusTrap: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ activeProjectRootFolder: 'project-folder' }) }))
vi.mock('../../api/folders', () => ({ listAllFolders: vi.fn() }))
vi.mock('../../api/workflows', () => ({ saveResultToFolder: vi.fn() }))
it('recovers folder reads and preserves a failed save without duplicate writes or dismissal', async () => {
  vi.mocked(listAllFolders).mockRejectedValueOnce(new Error('Folder service unavailable')).mockResolvedValueOnce([{ uuid: 'project-folder', title: 'Proposal', path: 'Proposal', parent_id: '', is_shared_team_root: false, team_id: null }])
  let reject!: (reason: Error) => void
  vi.mocked(saveResultToFolder).mockImplementationOnce(() => new Promise((_, no) => { reject = no }))
  const onClose = vi.fn(), onSaved = vi.fn()
  render(<SaveWorkflowOutputDialog sessionId="run-1" workflowName="Proposal review" onClose={onClose} onSaved={onSaved} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Folder service unavailable')
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Retry folders' }))
  await waitFor(() => expect(screen.getByLabelText('Folder')).toHaveValue('project-folder'))
  fireEvent.change(screen.getByLabelText('File name'), { target: { value: 'Review handoff' } })
  fireEvent.change(screen.getByLabelText('Format'), { target: { value: 'text' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  fireEvent.click(screen.getByRole('button', { name: 'Saving…' }))
  fireEvent.keyDown(window, { key: 'Escape' })
  expect(onClose).not.toHaveBeenCalled()
  expect(saveResultToFolder).toHaveBeenCalledOnce()
  await act(async () => reject(new Error('Save unavailable')))
  expect(screen.getByRole('alert')).toHaveTextContent('Save unavailable')
  expect(screen.getByLabelText('File name')).toHaveValue('Review handoff')
  expect(screen.getByLabelText('Format')).toHaveValue('text')
  vi.mocked(saveResultToFolder).mockResolvedValueOnce({ ok: true, folder_uuid: 'project-folder', file_path: 'Review handoff.txt' })
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith('project-folder'))
  expect(onClose).toHaveBeenCalledOnce()
})
