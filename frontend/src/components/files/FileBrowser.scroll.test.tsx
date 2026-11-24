import { fireEvent, render, screen } from '@testing-library/react'
import { createRef } from 'react'
import { expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FileBrowser } from './FileBrowser'
import type { Document } from '../../types/document'

const doc = { id: 'd1', uuid: 'd1', title: 'Award notice.pdf', extension: 'pdf', processing: false, valid: true, task_status: 'complete', folder: '0', created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00', token_count: 1, num_pages: 1, chromadb_ready: true } as Document

vi.mock('../../hooks/useTeams', () => ({ useTeams: () => ({ currentTeam: null }) }))
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: { is_admin: false } }) }))
vi.mock('../../hooks/useDocuments', () => ({ useDocuments: () => ({ documents: [doc], folders: [], refresh: vi.fn(), loading: false }) }))
vi.mock('../../hooks/useFolders', () => ({ useBreadcrumbs: () => ({ breadcrumbs: [] }) }))
vi.mock('../../hooks/useUpload', () => ({ useUpload: () => ({ uploads: [], upload: vi.fn() }) }))
vi.mock('../shared/useConfirm', () => ({ useConfirm: () => vi.fn() }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({}) }))
vi.mock('../../api/automations', () => ({ listAutomations: async () => [] }))
vi.mock('./UploadProgress', () => ({ UploadProgress: () => null }))

// Support ticket: the whole panel scrolled, so the upload area left with the
// rows. Only the list scrolls now; these pin what is inside it and what is not.
it('scrolls only the file rows: the upload area and folder trail sit outside the scrolling list', () => {
  const list = createRef<HTMLDivElement>()
  const onListScroll = vi.fn()
  render(<QueryClientProvider client={new QueryClient()}><FileBrowser listScrollRef={list} onListScroll={onListScroll} /></QueryClientProvider>)

  expect(list.current).toHaveClass('file-list-surface')
  expect(list.current).toContainElement(screen.getByRole('row', { name: 'Document: Award notice.pdf' }))
  expect(list.current).toContainElement(screen.getByRole('columnheader', { name: /Modified/ }))
  expect(list.current).not.toContainElement(screen.getByText('Upload files or drop them here'))
  expect(list.current).not.toContainElement(screen.getByRole('navigation', { name: 'Folder navigation' }))

  // The owner restores the list's position from what it reports.
  list.current!.scrollTop = 240
  fireEvent.scroll(list.current!)
  expect(onListScroll).toHaveBeenCalledWith(240)
})
