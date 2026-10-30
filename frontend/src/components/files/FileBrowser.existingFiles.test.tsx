import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FileBrowser } from './FileBrowser'
import { searchDocuments, type SearchResult } from '../../api/documents'
import { moveFile } from '../../api/files'

vi.mock('../../hooks/useTeams', () => ({ useTeams: () => ({ currentTeam: null }) }))
vi.mock('../../hooks/useDocuments', () => ({ useDocuments: () => ({ documents: [], folders: [], refresh: vi.fn(), loading: false }) }))
vi.mock('../../hooks/useFolders', () => ({ useBreadcrumbs: () => ({ breadcrumbs: [{ uuid: 'project-root', title: 'Subaward' }, { uuid: 'project-child', title: 'Budget files' }] }) }))
vi.mock('../../hooks/useUpload', () => ({ useUpload: () => ({ uploads: [], upload: vi.fn() }) }))
vi.mock('../shared/useConfirm', () => ({ useConfirm: () => vi.fn() }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({}) }))
vi.mock('../../api/automations', () => ({ listAutomations: async () => [] }))
vi.mock('../../api/documents', () => ({ searchDocuments: vi.fn() }))
vi.mock('../../api/files', () => ({ moveFile: vi.fn() }))
vi.mock('./UploadZone', () => ({ UploadZone: () => null }))
vi.mock('./UploadProgress', () => ({ UploadProgress: () => null }))

it('adds an existing file from the project Add menu into the displayed subfolder', async () => {
  vi.mocked(searchDocuments).mockResolvedValue({ items: [{ uuid: 'award', title: 'Subaward.pdf', folder: 'outside-project' } as SearchResult], total: 1 })
  vi.mocked(moveFile).mockResolvedValue({ ok: true })
  render(<QueryClientProvider client={new QueryClient()}><FileBrowser rootFolder="project-root" rootLabel="Subaward" currentFolder="project-child" /></QueryClientProvider>)
  expect(screen.getByText(/Use Add → From my files/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Add' }))
  fireEvent.click(screen.getByRole('menuitem', { name: 'From my files' }))
  expect(screen.getByRole('dialog')).toHaveTextContent('Budget files')
  fireEvent.click(await screen.findByRole('checkbox', { name: 'Subaward.pdf' }))
  expect(moveFile).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Move 1 file here' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(moveFile).toHaveBeenCalledExactlyOnceWith('award', 'project-child')
})
