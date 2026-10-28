import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChatPanel } from './ChatPanel'
import { pollStatus } from '../../api/documents'

const mocks = vi.hoisted(() => ({
  send: vi.fn(),
  selectSkill: vi.fn(),
  uploading: false,
  conversationUuid: null as string | null,
  error: null as string | null,
  queuedMessages: [] as string[],
  isStreaming: false,
  loadHistory: vi.fn(),
  blocked: false,
  workspace: {
    workspaceMode: 'chat',
    bumpActivitySignal: vi.fn(),
    focusChat: vi.fn(),
    setActiveRightTab: vi.fn(),
    selectedDocUuids: [] as string[],
    selectedDocNames: {} as Record<string, string>,
    selectedFolderUuids: [] as string[],
    selectedFolderNames: {} as Record<string, string>,
    selectedDocsProcessing: [],
    activeKBs: [] as { uuid: string; title: string }[],
    activeKBUuid: null as string | null,
    setSelectedDocUuids: vi.fn(),
    setSelectedDocNames: vi.fn(),
    setCurrentConversationUuid: vi.fn(),
  },
}))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => mocks.workspace }))
vi.mock('../../contexts/BrandingContext', () => ({ useBranding: () => ({ appName: 'Vandalizer' }) }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../../lib/shareLink', () => ({ useShareLink: () => vi.fn() }))
vi.mock('../../hooks/useProjects', () => ({ useProject: () => ({ project: null }) }))
vi.mock('../../hooks/useOnboarding', () => ({ useOnboarding: () => ({ pills: [], isFirstSession: true, loading: false, status: null }) }))
vi.mock('../../hooks/useChat', () => ({ useChat: () => ({
  messages: [], segments: [], queuedMessages: mocks.queuedMessages, error: mocks.error, planTasks: [], contextNotices: [],
  projectSkillBlocked: mocks.blocked, conversationUuid: mocks.conversationUuid, isStreaming: mocks.isStreaming, loadHistory: mocks.loadHistory, contextTokens: 0, initializeProjectSkill: vi.fn(), send: mocks.send, selectSkill: mocks.selectSkill,
}) }))
vi.mock('../../hooks/useChatUploads', () => ({ useChatUploads: (onUploaded: (uuid: string, file: File) => void) => ({
  uploads: [], uploading: mocks.uploading,
  add: (files: File[]) => onUploaded('uploaded-doc', files[0]),
}) }))
vi.mock('../../api/config', () => ({ getUserConfig: async () => ({}), markFirstSessionComplete: async () => {} }))
vi.mock('../../api/documents', () => ({ pollStatus: vi.fn() }))
vi.mock('../../api/knowledge', () => ({ getKnowledgeBase: async () => ({ sources_ready: 1, total_sources: 1 }) }))
vi.mock('./ChatInput', () => ({ ChatInput: () => null }))
vi.mock('./ContextLimitDialog', () => ({ ContextLimitDialog: () => null }))
vi.mock('./HomeExperience', () => ({
  FirstSessionHome: ({ onAttachFiles, onRunDemo, disabled }: {
    onAttachFiles: (files: File[]) => void; onRunDemo: () => void; disabled: boolean
  }) => <>
    <button onClick={() => onAttachFiles([new File(['proposal'], 'Proposal.pdf')])}>Upload document</button>
    <button disabled={disabled} onClick={onRunDemo}>Try sample demo</button>
  </>,
}))

function renderPanel(pendingMessage?: { message: string; skillUuid?: string; draftOnly?: boolean }) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ChatPanel pendingMessage={pendingMessage} /></QueryClientProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.selectSkill.mockResolvedValue(true)
  mocks.error = null
  mocks.queuedMessages = []
  mocks.conversationUuid = null
  mocks.isStreaming = false
  mocks.loadHistory.mockResolvedValue(null)
  mocks.uploading = false
  mocks.blocked = false
  mocks.workspace.workspaceMode = 'chat'
  mocks.workspace.selectedDocUuids = []
  mocks.workspace.selectedDocNames = {}
  mocks.workspace.selectedFolderUuids = []
  mocks.workspace.activeKBs = []
  mocks.workspace.activeKBUuid = null
  mocks.workspace.setSelectedDocUuids.mockImplementation(update => {
    mocks.workspace.selectedDocUuids = typeof update === 'function' ? update(mocks.workspace.selectedDocUuids) : update
  })
  mocks.workspace.setSelectedDocNames.mockImplementation(update => {
    mocks.workspace.selectedDocNames = typeof update === 'function' ? update(mocks.workspace.selectedDocNames) : update
  })
  vi.mocked(pollStatus).mockResolvedValue({ complete: true, status: 'complete', raw_text: 'Proposal text' } as Awaited<ReturnType<typeof pollStatus>>)
})

function expectDocumentRequest() {
  expect(mocks.send).toHaveBeenCalledOnce()
  expect(mocks.send).toHaveBeenCalledWith(
    expect.stringContaining('content attached to this chat'), ['uploaded-doc'], undefined,
    [], undefined, [], undefined, undefined, undefined,
  )
}

describe('Show me what you can do', () => {
  it('prepares a page edit draft without sending a chat message', async () => {
    renderPanel({ message: 'Update this page: /pages/page-id. Make the title shorter.', draftOnly: true })
    await waitFor(() => expect(mocks.workspace.focusChat).toHaveBeenCalledOnce())
    expect(mocks.send).not.toHaveBeenCalled()
    expect(mocks.selectSkill).not.toHaveBeenCalled()
  })

  it('consumes a Library Skill handoff without submitting an empty message', async () => {
    renderPanel({ message: '', skillUuid: 'award-skill' })
    await waitFor(() => expect(mocks.selectSkill).toHaveBeenCalledWith('award-skill'))
    await waitFor(() => expect(mocks.workspace.focusChat).toHaveBeenCalledOnce())
    expect(mocks.send).not.toHaveBeenCalled()
  })

  it('keeps the empty Skill selector out of chat', () => {
    renderPanel()
    expect(screen.queryByLabelText('Chat Skill')).not.toBeInTheDocument()
  })

  it('keeps supporting Assistant guidance compact beside Files', () => {
    mocks.workspace.workspaceMode = 'files'
    renderPanel()
    expect(screen.getByRole('heading', { name: 'Ask about your work' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try sample demo' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Start a conversation' }))
    expect(mocks.workspace.focusChat).toHaveBeenCalledOnce()
  })

  it('uses the uploaded document instead of starting sample onboarding', async () => {
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: 'Upload document' }))
    await waitFor(() => expect(screen.queryByText(/Attached files are processing/)).not.toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Show me what you can do' }))
    expectDocumentRequest()
  })

  it('waits for the uploaded document to become readable before demonstrating', async () => {
    let finish!: (result: Awaited<ReturnType<typeof pollStatus>>) => void
    vi.mocked(pollStatus).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: 'Upload document' }))
    fireEvent.click(screen.getByRole('button', { name: 'Show me what you can do' }))
    expect(mocks.send).not.toHaveBeenCalled()
    await act(async () => { finish({ complete: true, status: 'complete', raw_text: 'Proposal text' } as Awaited<ReturnType<typeof pollStatus>>) })
    await waitFor(expectDocumentRequest)
  })

  it('preserves folder and knowledge base scope', () => {
    mocks.workspace.selectedFolderUuids = ['folder-1']
    mocks.workspace.activeKBs = [{ uuid: 'kb-1', title: 'Policies' }]
    mocks.workspace.activeKBUuid = 'kb-1'
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: 'Show me what you can do' }))
    expect(mocks.send).toHaveBeenCalledWith(
      expect.stringContaining('content attached to this chat'), [], undefined,
      ['kb-1'], undefined, ['folder-1'], undefined, undefined, undefined,
    )
  })

  it('keeps the sample demo available when no content is attached', () => {
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: 'Try sample demo' }))
    expect(mocks.send).toHaveBeenCalledWith('Show me what Vandalizer can do', [], undefined, undefined, undefined, undefined, undefined, true)
  })

  it('does not start a demo while an attachment is transferring', () => {
    mocks.uploading = true
    mocks.workspace.selectedDocUuids = ['uploaded-doc']
    renderPanel()
    const button = screen.getByRole('button', { name: 'Show me what you can do' })
    expect(button).toBeDisabled()
    fireEvent.click(button)
    expect(mocks.send).not.toHaveBeenCalled()
  })
})

it('keeps a pending task when the project default is unavailable, but permits an explicit Skill choice', async () => {
  mocks.blocked = true
  const view = renderPanel({ message: 'Keep this draft' })
  expect(mocks.send).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: 'Continue without Skill' })).toBeInTheDocument()
  view.unmount()
  renderPanel({ message: '', skillUuid: 'replacement' })
  await waitFor(() => expect(mocks.selectSkill).toHaveBeenCalledWith('replacement'))
  expect(mocks.send).not.toHaveBeenCalled()
})

it('does not replace a live stream when the scope remembers the same conversation', async () => {
  mocks.conversationUuid = 'live-conversation'
  mocks.isStreaming = true
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const { rerender } = render(<QueryClientProvider client={client}><ChatPanel /></QueryClientProvider>)
  rerender(<QueryClientProvider client={client}><ChatPanel conversationToLoad="live-conversation" /></QueryClientProvider>)
  expect(mocks.loadHistory).not.toHaveBeenCalled()
  const activity = screen.getByRole('region', { name: 'Live assistant activity' })
  expect(screen.getByRole('region', { name: 'Conversation' })).toContainElement(activity)
  expect(activity.closest('.chat-composer-slot')).toBeNull()
  rerender(<QueryClientProvider client={client}><ChatPanel conversationToLoad="different-conversation" /></QueryClientProvider>)
  await waitFor(() => expect(mocks.loadHistory).toHaveBeenCalledWith('different-conversation'))
  mocks.isStreaming = false
  rerender(<QueryClientProvider client={client}><ChatPanel conversationToLoad="different-conversation" /></QueryClientProvider>)
  expect(screen.queryByRole('region', { name: 'Live assistant activity' })).not.toBeInTheDocument()
})

it('marks queued delivery unconfirmed when a stream fails instead of implying it is still running', () => {
  mocks.isStreaming = true
  mocks.queuedMessages = ['What should I report to support?']
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const { rerender } = render(<QueryClientProvider client={client}><ChatPanel /></QueryClientProvider>)
  expect(screen.getByText('Queued')).toBeInTheDocument()
  mocks.isStreaming = false
  mocks.error = 'The response stalled.'
  rerender(<QueryClientProvider client={client}><ChatPanel /></QueryClientProvider>)
  expect(screen.queryByText('Queued')).not.toBeInTheDocument()
  expect(screen.getByText('Delivery unconfirmed')).toBeInTheDocument()
  expect(screen.getByText('What should I report to support?')).toBeInTheDocument()
})
