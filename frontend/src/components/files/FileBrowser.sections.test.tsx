import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FileBrowser } from './FileBrowser'
import { deleteFile } from '../../api/files'
import type { Document, Folder } from '../../types/document'

const base = { processing: false, valid: true, task_status: 'complete', folder: '0', created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00', token_count: 1, num_pages: 1, chromadb_ready: true }
const doc = (uuid: string, title: string, extension: string, extra: Partial<Document> = {}) => ({ id: uuid, uuid, title, extension, ...base, ...extra }) as Document
const contents = {
  folders: [{ id: 'f1', uuid: 'f1', title: 'Certification Lab', parent_id: '0', is_shared_team_root: false, item_count: 3 }] as Folder[],
  documents: [
    doc('d1', 'subaward-agreement.pdf', 'pdf', { ingest_error: 'timeout' }),
    doc('d2', 'terms.pdf', 'pdf'),
    doc('d3', 'budget.xlsx', 'xlsx'),
    doc('d4', 'memo.docx', 'docx'),
  ],
}

vi.mock('../../hooks/useTeams', () => ({ useTeams: () => ({ currentTeam: null }) }))
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: { is_admin: false } }) }))
vi.mock('../../hooks/useDocuments', () => ({ useDocuments: () => ({ ...contents, refresh: vi.fn(), loading: false }) }))
vi.mock('../../hooks/useFolders', () => ({ useBreadcrumbs: () => ({ breadcrumbs: [] }) }))
vi.mock('../../hooks/useUpload', () => ({ useUpload: () => ({ uploads: [], upload: vi.fn() }) }))
vi.mock('../shared/useConfirm', () => ({ useConfirm: () => async () => true }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({}) }))
vi.mock('../../api/automations', () => ({ listAutomations: async () => [] }))
vi.mock('../../api/files', async (original) => ({ ...(await original<typeof import('../../api/files')>()), deleteFile: vi.fn(), fetchDocumentUsage: vi.fn(async () => ({ knowledge_bases: [], workflows: [], extractions: [], total: 0 })) }))
vi.mock('./UploadZone', () => ({ UploadZone: () => null }))
vi.mock('./UploadProgress', () => ({ UploadProgress: () => null }))

const renderBrowser = () => render(<QueryClientProvider client={new QueryClient()}><FileBrowser /></QueryClientProvider>)
const chip = (name: RegExp) => within(screen.getByRole('group', { name: 'Show documents' })).getByRole('button', { name })
const docRows = () => screen.queryAllByRole('row', { name: /^Document:/ }).map(row => row.getAttribute('aria-label'))

beforeEach(() => {
  localStorage.clear()
  vi.mocked(deleteFile).mockReset()
})

it('heads folders and documents separately, with counts', () => {
  renderBrowser()
  expect(screen.getByRole('button', { name: /Folders 1/ })).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getByText('Documents').parentElement).toHaveTextContent('Documents 4')
  expect(chip(/^All 4/)).toHaveAttribute('aria-pressed', 'true')
  expect(chip(/^PDF 2/)).toBeInTheDocument()
  expect(chip(/^Spreadsheet 1/)).toBeInTheDocument()
  expect(chip(/^Document 1/)).toBeInTheDocument()
  expect(chip(/^Needs attention 1/)).toBeInTheDocument()
})

it('filters only the documents; folders stay listed', () => {
  renderBrowser()
  fireEvent.click(chip(/^Spreadsheet/))
  expect(docRows()).toEqual(['Document: budget.xlsx'])
  expect(screen.getByRole('row', { name: 'Folder: Certification Lab' })).toBeInTheDocument()

  fireEvent.click(chip(/^Needs attention/))
  expect(docRows()).toEqual(['Document: subaward-agreement.pdf'])
  expect(screen.getByRole('status')).toHaveTextContent('1 not indexed')
})

it('collapses the Folders section and remembers it', () => {
  const first = renderBrowser()
  fireEvent.click(screen.getByRole('button', { name: /Folders 1/ }))
  expect(screen.queryByRole('row', { name: 'Folder: Certification Lab' })).not.toBeInTheDocument()
  first.unmount()

  renderBrowser()
  expect(screen.getByRole('button', { name: /Folders 1/ })).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByRole('row', { name: 'Folder: Certification Lab' })).not.toBeInTheDocument()
})

it('never bulk-deletes a selected file the filter is hiding', async () => {
  vi.mocked(deleteFile).mockResolvedValue({ ok: true } as never)
  renderBrowser()
  fireEvent.click(screen.getByRole('checkbox', { name: 'Select budget.xlsx' }))
  fireEvent.click(chip(/^PDF/))
  fireEvent.click(screen.getByRole('button', { name: /Folders 1/ }))
  // Select all now means the two PDFs on screen: not the hidden spreadsheet,
  // and not the folder in the collapsed section.
  fireEvent.click(screen.getByRole('checkbox', { name: 'Select all' }))
  const toolbar = screen.getByRole('group', { name: 'Selected files and bulk actions' })
  expect(toolbar).toHaveTextContent('2 selected · 1 hidden by the filter (not included)')

  fireEvent.click(within(toolbar).getByRole('button', { name: 'Delete' }))
  await waitFor(() => expect(deleteFile).toHaveBeenCalledTimes(2))
  await waitFor(() => expect(screen.getByRole('group', { name: 'Selected files and bulk actions' })).toHaveTextContent(/^0 selected/))
  expect(vi.mocked(deleteFile).mock.calls.map(call => call[0]).sort()).toEqual(['d1', 'd2'])
  // The hidden spreadsheet was not part of the delete and is still selected.
  fireEvent.click(chip(/^All/))
  expect(screen.getByRole('checkbox', { name: 'Select budget.xlsx' })).toBeChecked()
})
