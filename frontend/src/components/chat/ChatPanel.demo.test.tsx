import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChatPanel } from './ChatPanel'
import type { ChatMessage, StreamSegment } from '../../types/chat'
import { pollStatus } from '../../api/documents'

const mocks = vi.hoisted(() => ({
  send: vi.fn(),
  resumeQueuedMessages: vi.fn(),
  selectSkill: vi.fn(),
  uploading: false,
  conversationUuid: null as string | null,
  activityId: null as string | null,
  messages: [] as ChatMessage[],
  error: null as string | null,
  queuedMessages: [] as string[],
  isStreaming: false,
  segments: [] as StreamSegment[],
  thinkingContent: '',
  activeToolCalls: [] as { tool_name: string; tool_call_id: string; args: Record<string, unknown> }[],
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
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanel: () => ({ openPanel: vi.fn() }), useCertificationPanelOptional: () => null }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../../lib/shareLink', () => ({ useShareLink: () => vi.fn() }))
vi.mock('../../hooks/useProjects', () => ({ useProject: () => ({ project: null }) }))
vi.mock('../../hooks/useOnboarding', () => ({ useOnboarding: () => ({ pills: [], isFirstSession: true, loading: false, status: null }) }))
vi.mock('../../hooks/useChat', () => ({ useChat: () => ({
  messages: mocks.messages, activityId: mocks.activityId, segments: mocks.segments, thinkingContent: mocks.thinkingContent, activeToolCalls: mocks.activeToolCalls, queuedMessages: mocks.queuedMessages, error: mocks.error, planTasks: [], contextNotices: [],
  projectSkillBlocked: mocks.blocked, conversationUuid: mocks.conversationUuid, isStreaming: mocks.isStreaming, loadHistory: mocks.loadHistory, contextTokens: 0, initializeProjectSkill: vi.fn(), send: mocks.send, selectSkill: mocks.selectSkill, resumeQueuedMessages: mocks.resumeQueuedMessages,
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
  mocks.activityId = null
  mocks.messages = []
  mocks.isStreaming = false
  mocks.thinkingContent = ''
  mocks.segments = []
  mocks.activeToolCalls = []
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
  expect(mocks.send.mock.calls[0].slice(0, 9)).toEqual([
    expect.stringContaining('content attached to this chat'), ['uploaded-doc'], undefined,
    [], undefined, [], undefined, undefined, undefined,
  ])
}

describe('Show me what you can do', () => {
  it('passes a page Save decision through to the request as an immutable preview ID', () => {
    const previewId = 'b'.repeat(32)
    mocks.conversationUuid = 'pages'
    mocks.activityId = 'page-activity'
    mocks.messages = [{ role: 'assistant', content: '',
      tool_calls: [{ tool_name: 'revise_html_artifact', tool_call_id: 'page', args: { title: 'NIH dashboard', html: '<table>All rows</table>' } }],
      tool_results: [{ tool_name: 'revise_html_artifact', tool_call_id: 'page', content: { needs_confirmation: true, preview_id: previewId, artifact_preview_html: '<table>All rows</table>' }, quality: null }],
    }]
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: 'Save new version' }))
    expect(mocks.send).toHaveBeenCalledOnce()
    expect(mocks.send.mock.calls[0][0]).toBe('Yes, go ahead')
    expect(mocks.send.mock.calls[0][10]).toBe(previewId)
  })
  it('prepares a page edit draft without sending a chat message', async () => {
    renderPanel({ message: 'Update this page: /pages/page-id. Make the title shorter.', draftOnly: true })
    await waitFor(() => expect(mocks.workspace.focusChat).toHaveBeenCalledOnce())
    expect(mocks.send).not.toHaveBeenCalled()
    expect(mocks.selectSkill).not.toHaveBeenCalled()
  })

  it('runs a Library Skill handoff exactly once', async () => {
    renderPanel({ message: '', skillUuid: 'award-skill' })
    await waitFor(() => expect(mocks.send).toHaveBeenCalledWith('', [], undefined, [], undefined, [], undefined, undefined, undefined, 'award-skill'))
    await waitFor(() => expect(mocks.workspace.focusChat).toHaveBeenCalledOnce())
    expect(mocks.send).toHaveBeenCalledOnce()
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
    expect(mocks.send.mock.calls[0].slice(0, 9)).toEqual([
      expect.stringContaining('content attached to this chat'), [], undefined,
      ['kb-1'], undefined, ['folder-1'], undefined, undefined, undefined,
    ])
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
  await waitFor(() => expect(mocks.send).toHaveBeenCalledWith('', [], undefined, [], undefined, [], undefined, undefined, undefined, 'replacement'))
})

it('does not replace a live stream when the scope remembers the same conversation', async () => {
  mocks.conversationUuid = 'live-conversation'
  mocks.isStreaming = true
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const { rerender } = render(<QueryClientProvider client={client}><ChatPanel /></QueryClientProvider>)
  rerender(<QueryClientProvider client={client}><ChatPanel conversationToLoad="live-conversation" /></QueryClientProvider>)
  expect(mocks.loadHistory).not.toHaveBeenCalled()
  const activity = screen.getByRole('status', { name: 'Assistant progress' })
  expect(screen.getByRole('region', { name: 'Conversation' })).toContainElement(activity)
  expect(activity.closest('.chat-composer-slot')).toBeNull()
  rerender(<QueryClientProvider client={client}><ChatPanel conversationToLoad="different-conversation" /></QueryClientProvider>)
  await waitFor(() => expect(mocks.loadHistory).toHaveBeenCalledWith('different-conversation'))
  mocks.isStreaming = false
  mocks.thinkingContent = ''
  mocks.segments = []
  mocks.activeToolCalls = []
  rerender(<QueryClientProvider client={client}><ChatPanel conversationToLoad="different-conversation" /></QueryClientProvider>)
  expect(screen.queryByRole('status', { name: 'Assistant progress' })).not.toBeInTheDocument()
})

it('keeps queued requests visibly unsent when a stream fails and offers to resume', () => {
  mocks.isStreaming = true
  mocks.queuedMessages = ['What should I report to support?']
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const { rerender } = render(<QueryClientProvider client={client}><ChatPanel /></QueryClientProvider>)
  expect(screen.getByText('Queued')).toBeInTheDocument()
  mocks.isStreaming = false
  mocks.thinkingContent = ''
  mocks.segments = []
  mocks.activeToolCalls = []
  mocks.error = 'The response stalled.'
  rerender(<QueryClientProvider client={client}><ChatPanel /></QueryClientProvider>)
  expect(screen.queryByText('Queued')).not.toBeInTheDocument()
  expect(screen.getByText('Waiting for next turn')).toBeInTheDocument()
  expect(screen.getByText('These messages have not been sent yet.')).toBeInTheDocument()
  expect(screen.getByText('What should I report to support?')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Send queued messages' }))
  expect(mocks.resumeQueuedMessages).toHaveBeenCalledOnce()
})

it('does not add a second progress indicator alongside an existing thinking or active-tool entry', () => {
  mocks.isStreaming = true
  mocks.thinkingContent = 'Reviewing the request'
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const { rerender } = render(<QueryClientProvider client={client}><ChatPanel /></QueryClientProvider>)
  expect(screen.getByRole('button', { name: 'Expand thinking' })).toBeInTheDocument()
  expect(screen.queryByRole('status', { name: 'Assistant progress' })).not.toBeInTheDocument()
  mocks.thinkingContent = ''
  mocks.segments = []
  mocks.activeToolCalls = [{ tool_name: 'search_knowledge_base', tool_call_id: 'search', args: { query: 'eligibility' } }]
  mocks.segments = mocks.activeToolCalls.map(call => ({ kind: 'tool_call', call }))
  rerender(<QueryClientProvider client={client}><ChatPanel /></QueryClientProvider>)
  expect(screen.getByRole('status')).toHaveTextContent('Searching knowledge base · Running')
  expect(screen.queryByRole('status', { name: 'Assistant progress' })).not.toBeInTheDocument()
})
