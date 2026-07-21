import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { LibraryTab } from './LibraryTab'
import type { LibraryItem } from '../../types/library'

const sendChatMessage = vi.fn()
const openWorkflow = vi.fn()
const openExtraction = vi.fn()

vi.mock('../../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({
    openWorkflow,
    openExtraction,
    sendChatMessage,
    selectedDocUuids: ['doc-1'],
    selectedFolderUuids: [],
    openWorkflowId: null,
    openExtractionId: null,
    openAutomationId: null,
  }),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: '1', user_id: 'viewer', email: 'viewer@example.com', name: 'Viewer', is_admin: false, current_team: null },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}))

vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

vi.mock('../shared/useConfirm', () => ({
  useConfirm: () => vi.fn().mockResolvedValue(true),
}))

vi.mock('../../lib/shareLink', () => ({
  useShareLink: () => vi.fn(),
  buildShareUrl: vi.fn(),
}))

vi.mock('../library/ExploreTab', () => ({ ExploreTab: () => null }))
vi.mock('../library/ShareWithTeamDialog', () => ({ ShareWithTeamDialog: () => null }))

const mockItems: { current: LibraryItem[] } = { current: [] }

vi.mock('../../hooks/useLibrary', () => ({
  useLibraries: () => ({
    libraries: [{ id: 'lib-1', scope: 'personal', title: 'My Library', description: null, owner_user_id: 'viewer', team_id: null, item_count: 1, created_at: null, updated_at: null }],
    loading: false,
    error: null,
    refresh: vi.fn(),
  }),
  useLibraryItems: () => ({
    items: mockItems.current,
    loading: false,
    refresh: vi.fn(),
    add: vi.fn(),
    remove: vi.fn(),
    update: vi.fn(),
  }),
  useLibraryFolders: () => ({
    folders: [],
    loading: false,
    refresh: vi.fn(),
    create: vi.fn(),
    rename: vi.fn(),
    remove: vi.fn(),
    moveItems: vi.fn(),
  }),
}))

vi.mock('../../api/library', () => ({
  cloneToPersonal: vi.fn(),
  shareToTeam: vi.fn(),
  addItem: vi.fn(),
  touchItem: vi.fn().mockResolvedValue(undefined),
  listCollections: vi.fn().mockResolvedValue({ collections: [] }),
  submitForVerification: vi.fn(),
}))

vi.mock('../../api/workflows', () => ({
  createWorkflow: vi.fn(),
  importWorkflow: vi.fn(),
}))

vi.mock('../../api/extractions', () => ({
  createSearchSet: vi.fn(),
  importSearchSet: vi.fn(),
  listItems: vi.fn(),
  updateSearchSet: vi.fn(),
  updateItem: vi.fn(),
  addItem: vi.fn(),
}))

import { listItems as listSearchSetItems } from '../../api/extractions'
import { touchItem } from '../../api/library'

function makePrompt(overrides: Partial<LibraryItem> = {}): LibraryItem {
  return {
    id: 'li-1',
    item_id: 'ss-1',
    item_uuid: 'ss-uuid-1',
    kind: 'search_set',
    name: 'Summarize Award',
    description: null,
    set_type: 'prompt',
    tags: [],
    note: null,
    folder: null,
    pinned: false,
    favorited: false,
    verified: false,
    added_by_user_id: 'viewer',
    created_at: '2026-01-01T00:00:00',
    last_used_at: null,
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockItems.current = [makePrompt()]
  vi.mocked(listSearchSetItems).mockResolvedValue([
    { id: 'ssi-1', searchphrase: 'Summarize the key terms of this award.' },
  ] as Awaited<ReturnType<typeof listSearchSetItems>>)
})

describe('LibraryTab prompt preview', () => {
  it('opens a preview on row click instead of sending to chat', async () => {
    render(<LibraryTab />)
    fireEvent.click(screen.getByText('Summarize Award'))
    expect(await screen.findByText('Summarize the key terms of this award.')).toBeTruthy()
    expect(screen.getByText('Use in Assistant')).toBeTruthy()
    expect(sendChatMessage).not.toHaveBeenCalled()
    expect(touchItem).not.toHaveBeenCalled()
  })

  it('sends the prompt to the assistant from the Use in Assistant button', async () => {
    render(<LibraryTab />)
    fireEvent.click(screen.getByText('Summarize Award'))
    await screen.findByText('Summarize the key terms of this award.')
    fireEvent.click(screen.getByText('Use in Assistant'))
    expect(sendChatMessage).toHaveBeenCalledWith('Summarize the key terms of this award.', {
      documentUuids: ['doc-1'],
      folderUuids: [],
    })
    expect(touchItem).toHaveBeenCalledWith('li-1')
    // Modal closes after launching
    expect(screen.queryByText('Use in Assistant')).toBeNull()
  })

  it('disables Use in Assistant and explains when the prompt has no content', async () => {
    vi.mocked(listSearchSetItems).mockResolvedValue([] as Awaited<ReturnType<typeof listSearchSetItems>>)
    render(<LibraryTab />)
    fireEvent.click(screen.getByText('Summarize Award'))
    expect(await screen.findByText('This prompt has no content yet — click Edit to add some.')).toBeTruthy()
    const useBtn = screen.getByText('Use in Assistant') as HTMLButtonElement
    expect(useBtn.disabled).toBe(true)
    fireEvent.click(useBtn)
    expect(sendChatMessage).not.toHaveBeenCalled()
  })

  it('switches to the edit form from the preview Edit button', async () => {
    render(<LibraryTab />)
    fireEvent.click(screen.getByText('Summarize Award'))
    await screen.findByText('Summarize the key terms of this award.')
    fireEvent.click(screen.getByText('Edit'))
    expect(await screen.findByText('Edit Prompt')).toBeTruthy()
    const textarea = screen.getByPlaceholderText('Write your prompt here') as HTMLTextAreaElement
    expect(textarea.value).toBe('Summarize the key terms of this award.')
  })

  it('still opens the workflow editor directly for workflow items', async () => {
    mockItems.current = [makePrompt({ id: 'li-2', item_id: 'wf-1', item_uuid: 'wf-uuid-1', kind: 'workflow', set_type: null, name: 'Budget Workflow' })]
    render(<LibraryTab />)
    fireEvent.click(screen.getByText('Budget Workflow'))
    expect(openWorkflow).toHaveBeenCalledWith('wf-1')
    await waitFor(() => expect(touchItem).toHaveBeenCalledWith('li-2'))
  })
})
