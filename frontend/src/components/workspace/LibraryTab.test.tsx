import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { LibraryTab } from './LibraryTab'
import type { LibraryFolder, LibraryItem } from '../../types/library'

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

vi.mock('../../hooks/useTeams', () => ({
  useTeams: () => ({ teams: [], currentTeam: null, loading: false }),
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

vi.mock('../library/ExploreTab', () => ({ ExploreTab: () => <div>Catalog browser</div> }))
vi.mock('../library/ShareWithTeamDialog', () => ({ ShareWithTeamDialog: () => null }))

const mockItems: { current: LibraryItem[] } = { current: [] }
const mockFolders: { current: LibraryFolder[]; loading: boolean } = { current: [], loading: false }
const removeItemMock = vi.fn()

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
    remove: (...args: unknown[]) => removeItemMock(...args),
    update: vi.fn(),
  }),
  useLibraryFolders: () => ({
    folders: mockFolders.current,
    loading: mockFolders.loading,
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

import { listItems as listSearchSetItems, updateSearchSet } from '../../api/extractions'
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
  localStorage.clear()
  mockFolders.current = []
  mockFolders.loading = false
  mockItems.current = [makePrompt()]
  vi.mocked(listSearchSetItems).mockResolvedValue([
    { id: 'ssi-1', searchphrase: 'Summarize the key terms of this award.' },
  ] as Awaited<ReturnType<typeof listSearchSetItems>>)
})

describe('LibraryTab Skills', () => {
  it('opens a preview on click, and runs the Skill only from its Run Skill button', async () => {
    mockItems.current = [makePrompt({ when_to_use: 'summarizing a new award notice' })]
    render(<LibraryTab />)
    fireEvent.click(screen.getByRole('button', { name: 'Open Summarize Award' }))
    const dialog = await screen.findByRole('dialog', { name: 'Preview Summarize Award' })
    expect(within(dialog).getByText('summarizing a new award notice')).toBeTruthy()
    expect(await within(dialog).findByText('Summarize the key terms of this award.')).toBeTruthy()
    expect(sendChatMessage).not.toHaveBeenCalled()
    expect(touchItem).not.toHaveBeenCalled()

    fireEvent.click(within(dialog).getByRole('button', { name: 'Run Skill' }))
    expect(sendChatMessage).toHaveBeenCalledExactlyOnceWith('', {
      skillUuid: 'ss-uuid-1', documentUuids: ['doc-1'], folderUuids: [],
    })
    expect(touchItem).toHaveBeenCalledWith('li-1')
    expect(screen.queryByRole('dialog', { name: 'Preview Summarize Award' })).toBeNull()
  })

  it('closing the preview runs nothing', async () => {
    render(<LibraryTab />)
    fireEvent.click(screen.getByRole('button', { name: 'Open Summarize Award' }))
    const dialog = await screen.findByRole('dialog', { name: 'Preview Summarize Award' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog', { name: 'Preview Summarize Award' })).toBeNull()
    expect(sendChatMessage).not.toHaveBeenCalled()
  })

  it('does not run a Skill with no identity', async () => {
    mockItems.current = [makePrompt({ item_uuid: null, description: 'Summarize the award.' })]
    render(<LibraryTab />)
    fireEvent.click(screen.getByText('Summarize Award'))
    const dialog = await screen.findByRole('dialog', { name: 'Preview Summarize Award' })
    expect(within(dialog).getByRole('button', { name: 'Run Skill' })).toBeDisabled()
    expect(sendChatMessage).not.toHaveBeenCalled()
  })

  it('keeps editing available in the row menu without running the Skill', async () => {
    render(<LibraryTab />)
    fireEvent.click(screen.getByRole('button', { name: 'More actions' }))
    fireEvent.click(screen.getByText('Edit'))
    expect(await screen.findByText('Edit Skill')).toBeTruthy()
    await waitFor(() => expect(screen.getByPlaceholderText('Write your Skill instructions here')).toHaveValue('Summarize the key terms of this award.'))
    expect(sendChatMessage).not.toHaveBeenCalled()
  })

  it('loads a Skill\'s "When to use" line into the editor and saves the edited line', async () => {
    mockItems.current = [makePrompt({ when_to_use: 'Reviewing a new award notice' })]
    vi.mocked(updateSearchSet).mockResolvedValue({} as Awaited<ReturnType<typeof updateSearchSet>>)
    render(<LibraryTab />)
    fireEvent.click(screen.getByRole('button', { name: 'More actions' }))
    fireEvent.click(screen.getByText('Edit'))
    const line = await screen.findByLabelText('When to use (optional)')
    expect(line).toHaveValue('Reviewing a new award notice')
    await waitFor(() => expect(screen.getByPlaceholderText('Write your Skill instructions here')).toHaveValue('Summarize the key terms of this award.'))
    fireEvent.change(line, { target: { value: '  Checking a subaward against intake  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Update' }))
    await waitFor(() => expect(updateSearchSet).toHaveBeenCalledWith('ss-uuid-1', {
      title: 'Summarize Award', when_to_use: 'Checking a subaward against intake',
    }))
  })

  it('tells the editor of a team Skill that teammates review the new text, and says nothing in Mine', async () => {
    const { unmount } = render(<LibraryTab />)
    fireEvent.click(screen.getByRole('button', { name: 'More actions' }))
    fireEvent.click(screen.getByText('Edit'))
    await screen.findByText('Edit Skill')
    expect(screen.queryByTestId('team-core-skill-note')).toBeNull()
    unmount()

    render(<LibraryTab />)
    fireEvent.click(screen.getByRole('button', { name: 'Team' }))
    fireEvent.click(await screen.findByRole('button', { name: 'More actions' }))
    fireEvent.click(screen.getByText('Edit'))
    await screen.findByText('Edit Skill')
    expect(screen.getByTestId('team-core-skill-note').textContent).toMatch(/Teammates who use this as a core Skill will need to review the new text/)
  })

  // Support ticket: Edit → Update erased the line, pausing the Skill as a
  // core Skill. Update leaves it alone unless the user changed it.
  it('keeps the saved "When to use" line when only the instructions change', async () => {
    mockItems.current = [makePrompt({ when_to_use: 'Reviewing a new award notice' })]
    vi.mocked(updateSearchSet).mockResolvedValue({} as Awaited<ReturnType<typeof updateSearchSet>>)
    render(<LibraryTab />)
    fireEvent.click(screen.getByRole('button', { name: 'More actions' }))
    fireEvent.click(screen.getByText('Edit'))
    const instructions = screen.getByPlaceholderText('Write your Skill instructions here')
    await waitFor(() => expect(instructions).toHaveValue('Summarize the key terms of this award.'))
    fireEvent.change(instructions, { target: { value: 'Summarize the key terms of this subaward.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Update' }))
    await waitFor(() => expect(updateSearchSet).toHaveBeenCalledWith('ss-uuid-1', { title: 'Summarize Award' }))
  })

  it('a line the Library list did not include is never saved over as empty', async () => {
    mockItems.current = [makePrompt({ when_to_use: undefined })]
    vi.mocked(updateSearchSet).mockResolvedValue({} as Awaited<ReturnType<typeof updateSearchSet>>)
    render(<LibraryTab />)
    fireEvent.click(screen.getByRole('button', { name: 'More actions' }))
    fireEvent.click(screen.getByText('Edit'))
    await waitFor(() => expect(screen.getByPlaceholderText('Write your Skill instructions here')).toHaveValue('Summarize the key terms of this award.'))
    fireEvent.click(screen.getByRole('button', { name: 'Update' }))
    await waitFor(() => expect(updateSearchSet).toHaveBeenCalled())
    expect(vi.mocked(updateSearchSet).mock.calls[0][1]).not.toHaveProperty('when_to_use')
  })

  it('clearing the "When to use" line saves it empty', async () => {
    mockItems.current = [makePrompt({ when_to_use: 'Reviewing a new award notice' })]
    vi.mocked(updateSearchSet).mockResolvedValue({} as Awaited<ReturnType<typeof updateSearchSet>>)
    render(<LibraryTab />)
    fireEvent.click(screen.getByRole('button', { name: 'More actions' }))
    fireEvent.click(screen.getByText('Edit'))
    const line = await screen.findByLabelText('When to use (optional)')
    await waitFor(() => expect(screen.getByPlaceholderText('Write your Skill instructions here')).toHaveValue('Summarize the key terms of this award.'))
    fireEvent.change(line, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Update' }))
    await waitFor(() => expect(updateSearchSet).toHaveBeenCalledWith('ss-uuid-1', { title: 'Summarize Award', when_to_use: '' }))
  })

  it('still opens the workflow editor directly for workflow items', async () => {
    mockItems.current = [makePrompt({ id: 'li-2', item_id: 'wf-1', item_uuid: 'wf-uuid-1', kind: 'workflow', set_type: null, name: 'Budget Workflow' })]
    render(<LibraryTab />)
    fireEvent.click(screen.getByText('Budget Workflow'))
    expect(openWorkflow).toHaveBeenCalledWith('wf-1')
  })
})

describe('LibraryTab last used', () => {
  it('does not mark a workflow used just because it was opened', async () => {
    mockItems.current = [makePrompt({ id: 'li-2', item_id: 'wf-1', item_uuid: null, kind: 'workflow', set_type: null, name: 'Budget Workflow' })]
    render(<LibraryTab />)
    fireEvent.click(screen.getByText('Budget Workflow'))
    expect(openWorkflow).toHaveBeenCalledWith('wf-1')
    await new Promise((r) => setTimeout(r, 0))
    expect(touchItem).not.toHaveBeenCalled()
  })

  it('does not mark an extraction used just because it was opened', async () => {
    mockItems.current = [makePrompt({ id: 'li-3', set_type: 'extraction', name: 'Award Terms' })]
    render(<LibraryTab />)
    fireEvent.click(screen.getByText('Award Terms'))
    expect(openExtraction).toHaveBeenCalledWith('ss-uuid-1')
    await new Promise((r) => setTimeout(r, 0))
    expect(touchItem).not.toHaveBeenCalled()
  })

  it('sorts a never-run item below one that was run, however new it is', () => {
    mockItems.current = [
      makePrompt({ id: 'li-new', item_id: 'wf-new', kind: 'workflow', set_type: null, name: 'Brand New Workflow', created_at: '2026-09-28T00:00:00+00:00', last_used_at: null }),
      makePrompt({ id: 'li-ran', item_id: 'wf-ran', kind: 'workflow', set_type: null, name: 'Ran Last Month', created_at: '2026-01-01T00:00:00+00:00', last_used_at: '2026-08-01T00:00:00+00:00' }),
    ]
    render(<LibraryTab />)
    const ran = screen.getByText('Ran Last Month')
    const fresh = screen.getByText('Brand New Workflow')
    expect(ran.compareDocumentPosition(fresh) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
  it('opens legacy extraction entries without a set type or separate UUID', () => {
    mockItems.current = [makePrompt({ id: 'legacy-item', item_id: 'extraction-id', item_uuid: null, set_type: null, name: 'Legacy extraction' })]
    render(<LibraryTab />)
    fireEvent.click(screen.getByRole('button', { name: 'Open Legacy extraction' }))
    expect(openExtraction).toHaveBeenCalledWith('extraction-id')
  })
  it('keeps content failures visible and prevents using a stale description until retry', async () => {
    mockItems.current = [makePrompt({ description: 'Old fallback', set_type: 'formatter' })]
    vi.mocked(listSearchSetItems).mockRejectedValueOnce(new Error('Content unavailable'))
    render(<LibraryTab />)
    fireEvent.click(screen.getByRole('button', { name: 'Open Summarize Award' }))
    await screen.findByText('Content unavailable')
    expect(screen.getByRole('button', { name: 'Use in Assistant' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Retry item content' }))
    await screen.findByText('Summarize the key terms of this award.')
    expect(screen.getByRole('button', { name: 'Use in Assistant' })).toBeEnabled()
  })
  it('ignores a late prompt read after closing and opening a different item', async () => {
    let release!: (value: Awaited<ReturnType<typeof listSearchSetItems>>) => void
    vi.mocked(listSearchSetItems).mockImplementationOnce(() => new Promise(resolve => { release = resolve }))
    mockItems.current = [makePrompt({ set_type: 'formatter' }), makePrompt({ id: 'second', item_uuid: 'second-uuid', name: 'Second prompt', set_type: 'formatter' })]
    render(<LibraryTab />)
    fireEvent.click(screen.getByRole('button', { name: 'Open Summarize Award' }))
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    fireEvent.click(screen.getByRole('button', { name: 'Open Second prompt' }))
    await screen.findByText('Summarize the key terms of this award.')
    release([{ id: 'old-item', searchphrase: 'Old response' }] as Awaited<ReturnType<typeof listSearchSetItems>>)
    await waitFor(() => expect(screen.queryByText('Old response')).not.toBeInTheDocument())
  })
})

describe('LibraryTab delete flow', () => {
  function makeOwnedWorkflow(overrides: Partial<LibraryItem> = {}): LibraryItem {
    return makePrompt({
      id: 'li-wf',
      item_id: 'wf-1',
      item_uuid: null,
      kind: 'workflow',
      set_type: null,
      name: 'NSF Proposal Extractor',
      can_delete_underlying: true,
      ...overrides,
    })
  }

  async function openDeleteDialog() {
    render(<LibraryTab />)
    // Row actions only render while the row is hovered
    fireEvent.mouseOver(screen.getByText('NSF Proposal Extractor'))
    fireEvent.click(await screen.findByLabelText('More actions'))
    fireEvent.click(screen.getByText('Delete'))
    expect(await screen.findByText('Delete permanently')).toBeTruthy()
  }

  it('labels the menu action "Delete" only when the user owns the underlying item', async () => {
    mockItems.current = [makeOwnedWorkflow()]
    render(<LibraryTab />)
    fireEvent.mouseOver(screen.getByText('NSF Proposal Extractor'))
    fireEvent.click(await screen.findByLabelText('More actions'))
    expect(screen.getByText('Delete')).toBeTruthy()
  })

  it('offers permanent delete when the user can manage the underlying workflow', async () => {
    mockItems.current = [makeOwnedWorkflow()]
    removeItemMock.mockResolvedValue(undefined)
    await openDeleteDialog()
    fireEvent.click(screen.getByText('Delete permanently'))
    await waitFor(() =>
      expect(removeItemMock).toHaveBeenCalledWith('li-wf', { deleteUnderlying: true }),
    )
  })

  it('removes only the bookmark from the choice dialog', async () => {
    mockItems.current = [makeOwnedWorkflow()]
    removeItemMock.mockResolvedValue(undefined)
    await openDeleteDialog()
    fireEvent.click(screen.getByText('Remove from library only'))
    await waitFor(() => expect(removeItemMock).toHaveBeenCalledWith('li-wf', undefined))
  })

  it('skips the choice dialog for items the user cannot permanently delete', async () => {
    mockItems.current = [makeOwnedWorkflow({ can_delete_underlying: false })]
    removeItemMock.mockResolvedValue(undefined)
    render(<LibraryTab />)
    fireEvent.mouseOver(screen.getByText('NSF Proposal Extractor'))
    fireEvent.click(await screen.findByLabelText('More actions'))
    // Bookmark-only items say "Remove", never "Delete"
    expect(screen.queryByText('Delete')).toBeNull()
    fireEvent.click(screen.getByText('Remove'))
    // Bookmark-only removal goes through the (mocked, auto-confirming) confirm
    // dialog — no "Delete permanently" option should ever render.
    await waitFor(() => expect(removeItemMock).toHaveBeenCalledWith('li-wf'))
    expect(screen.queryByText('Delete permanently')).toBeNull()
  })
})

describe('LibraryTab empty state', () => {
  it('suggests the catalog when the library has no items and links to it', async () => {
    mockItems.current = []
    render(<LibraryTab />)
    expect(screen.getByText('Your library is ready for its first tool')).toBeTruthy()
    expect(screen.queryByText('No items match these filters')).toBeNull()
    fireEvent.click(screen.getByText('Browse the catalog →'))
    expect(await screen.findByText('Catalog browser')).toBeTruthy()
  })

  it('keeps the plain message when a search matches nothing', () => {
    mockItems.current = []
    render(<LibraryTab />)
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: 'zzz' } })
    expect(screen.getByText('No items match these filters')).toBeTruthy()
    expect(screen.queryByText('Browse the catalog →')).toBeNull()
  })

  it('does not show the nudge when a kind filter hides existing items', () => {
    render(<LibraryTab />)
    fireEvent.click(screen.getByRole('button', { name: /^Workflows/ }))
    expect(screen.getByText('No items match these filters')).toBeTruthy()
    expect(screen.queryByText('Browse the catalog →')).toBeNull()
  })
})


// UI suggestion ticket: the sidebar took a third of the panel for people with
// no folders and squeezed the tool list.
describe('LibraryTab sidebar', () => {
  const folder = (name: string): LibraryFolder => ({ uuid: name, name, parent_id: null, scope: 'personal', item_count: 0 })
  const body = (container: HTMLElement) => container.querySelector('.library-body') as HTMLElement

  it('starts collapsed with no folders, showing the compact view bar', () => {
    const { container } = render(<LibraryTab />)
    expect(body(container).dataset.sidebar).toBe('collapsed')
    expect(screen.getByRole('button', { name: 'View: All items · Change' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Show views and folders' })).toBeTruthy()
  })

  it('starts expanded when there are folders', () => {
    mockFolders.current = [folder('Awards')]
    const { container } = render(<LibraryTab />)
    expect(body(container).dataset.sidebar).toBe('expanded')
  })

  it('expands and collapses, keeps focus on the control, and remembers the choice', () => {
    const { container, unmount } = render(<LibraryTab />)
    fireEvent.click(screen.getByRole('button', { name: 'Show views and folders' }))
    expect(body(container).dataset.sidebar).toBe('expanded')
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Hide views and folders' }))
    expect(localStorage.getItem('library:sidebar')).toBe('expanded')
    unmount()
    // Remembered over the no-folders default.
    const again = render(<LibraryTab />)
    expect(body(again.container).dataset.sidebar).toBe('expanded')
    fireEvent.click(screen.getByRole('button', { name: 'Hide views and folders' }))
    expect(body(again.container).dataset.sidebar).toBe('collapsed')
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Show views and folders' }))
  })

  it('opens views from the compact bar, and closes on a choice or Escape', () => {
    const { container } = render(<LibraryTab />)
    const sidebar = container.querySelector('#library-saved-views') as HTMLElement
    const toggle = screen.getByRole('button', { name: 'View: All items · Change' })
    fireEvent.click(toggle)
    expect(sidebar.dataset.open).toBe('true')
    fireEvent.click(screen.getByRole('button', { name: /Favorites/ }))
    expect(sidebar.dataset.open).toBe('false')
    expect(screen.getByRole('button', { name: 'View: Favorites · Change' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'View: Favorites · Change' }))
    fireEvent.keyDown(screen.getByRole('button', { name: /Pinned/ }), { key: 'Escape' })
    expect(sidebar.dataset.open).toBe('false')
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'View: Favorites · Change' }))
  })

  it('does not snap shut while folders load for someone who has them', () => {
    localStorage.setItem('library:hasFolders:personal:none', '1')
    mockFolders.loading = true
    const { container } = render(<LibraryTab />)
    expect(body(container).dataset.sidebar).toBe('expanded')
  })

  it('moves focus to the compact bar when deleting the last folder collapses the sidebar', () => {
    mockFolders.current = [folder('Awards')]
    const { container, rerender } = render(<LibraryTab />)
    screen.getByRole('button', { name: 'Open folder Awards' }).focus()
    mockFolders.current = []
    rerender(<LibraryTab />)
    expect(body(container).dataset.sidebar).toBe('collapsed')
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'View: All items · Change' }))
  })

  it('does not take focus when the sidebar collapses as folders first load', () => {
    localStorage.setItem('library:hasFolders:personal:none', '1')
    mockFolders.loading = true
    const { container, rerender } = render(<LibraryTab />)
    expect(body(container).dataset.sidebar).toBe('expanded')
    mockFolders.loading = false
    rerender(<LibraryTab />)
    expect(body(container).dataset.sidebar).toBe('collapsed')
    expect(document.activeElement).toBe(document.body)
  })

  it('closes the compact menu when a first folder expands the sidebar on a wide panel', () => {
    // Stand-in for the wide-panel CSS: the compact bar is hidden while expanded.
    const style = document.createElement('style')
    style.textContent = '.library-body[data-sidebar="expanded"] .library-views-bar { display: none; }'
    document.head.appendChild(style)
    try {
      const { container, rerender } = render(<LibraryTab />)
      const sidebar = container.querySelector('#library-saved-views') as HTMLElement
      fireEvent.click(screen.getByRole('button', { name: 'View: All items · Change' }))
      expect(sidebar.dataset.open).toBe('true')
      mockFolders.current = [folder('Awards')]
      rerender(<LibraryTab />)
      expect(body(container).dataset.sidebar).toBe('expanded')
      expect(sidebar.dataset.open).toBe('false')
    } finally {
      style.remove()
    }
  })

  it('renders and toggles when site storage is blocked', () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('blocked', 'SecurityError') })
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('blocked', 'SecurityError') })
    try {
      const { container } = render(<LibraryTab />)
      expect(body(container).dataset.sidebar).toBe('collapsed')
      fireEvent.click(screen.getByRole('button', { name: 'Show views and folders' }))
      expect(body(container).dataset.sidebar).toBe('expanded')
    } finally {
      getItem.mockRestore()
      setItem.mockRestore()
    }
  })
})
