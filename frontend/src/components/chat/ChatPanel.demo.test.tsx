import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChatPanel } from './ChatPanel'
import type { ChatActivity, ChatMessage, StreamSegment, SkillSnapshot, ToolResultInfo } from '../../types/chat'
import { pollStatus } from '../../api/documents'

const mocks = vi.hoisted(() => ({
  send: vi.fn(),
  resumeQueuedMessages: vi.fn(),
  selectSkill: vi.fn(),
  listSearchSets: vi.fn(),
  activeSkill: null as SkillSnapshot | null,
  isSelectingSkill: false,
  uploading: false,
  conversationUuid: null as string | null,
  activityId: null as string | null,
  messages: [] as ChatMessage[],
  error: null as string | null,
  queuedMessages: [] as string[],
  isStreaming: false,
  segments: [] as StreamSegment[],
  thinkingContent: '',
  streamingContent: '',
  activity: null as ChatActivity | null,
  toolResults: [] as ToolResultInfo[],
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
vi.mock('../../lib/shareLink', async importOriginal => ({ ...await importOriginal<typeof import('../../lib/shareLink')>(), useShareLink: () => vi.fn() }))
vi.mock('../../api/extractions', () => ({ listSearchSets: mocks.listSearchSets }))
vi.mock('../../hooks/useProjects', () => ({ useProject: () => ({ project: null }) }))
vi.mock('../../hooks/useOnboarding', () => ({ useOnboarding: () => ({ pills: [], isFirstSession: true, loading: false, status: null }) }))
vi.mock('../../hooks/useChat', () => ({ useChat: () => ({
  activity: mocks.activity, streamingContent: mocks.streamingContent, toolResults: mocks.toolResults,
  messages: mocks.messages, activityId: mocks.activityId, segments: mocks.segments, thinkingContent: mocks.thinkingContent, activeToolCalls: mocks.activeToolCalls, queuedMessages: mocks.queuedMessages, error: mocks.error, planTasks: [], contextNotices: [],
  activeSkill: mocks.activeSkill, isSelectingSkill: mocks.isSelectingSkill,
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

function renderPanel(pendingMessage?: { message: string; skillUuid?: string; skillSelectionOnly?: boolean; draftOnly?: boolean }) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ChatPanel pendingMessage={pendingMessage} /></QueryClientProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.selectSkill.mockResolvedValue(true)
  mocks.activeSkill = null
  mocks.isSelectingSkill = false
  mocks.listSearchSets.mockResolvedValue([])
  mocks.error = null
  mocks.queuedMessages = []
  mocks.conversationUuid = null
  mocks.activityId = null
  mocks.messages = []
  mocks.isStreaming = false
  mocks.thinkingContent = ''
  mocks.streamingContent = ''
  mocks.activity = null
  mocks.toolResults = []
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

  it('selects a shared setup Skill without running it', async () => {
    renderPanel({ message: '', skillUuid: 'award-skill', skillSelectionOnly: true })
    await waitFor(() => expect(mocks.selectSkill).toHaveBeenCalledWith('award-skill'))
    expect(mocks.selectSkill).toHaveBeenCalledOnce()
    expect(mocks.send).not.toHaveBeenCalled()
  })

  it('shows the active Skill in the source bar and inspects its saved instructions', () => {
    mocks.activeSkill = { uuid: 'award-skill', title: 'Award Review', version: 'saved-v1', instructions: 'Check the award dates.' }
    mocks.workspace.activeKBs = [{ uuid: 'kb-1', title: 'Awards KB' }]
    renderPanel()
    const bar = screen.getByRole('region', { name: 'Conversation sources' })
    expect(bar).toHaveTextContent('Award Review')
    expect(bar).toHaveTextContent('Awards KB')
    fireEvent.click(screen.getByRole('button', { name: 'Inspect instructions' }))
    expect(screen.getByRole('dialog')).toHaveTextContent('Check the award dates.')
    expect(screen.getByRole('dialog')).toHaveTextContent('saved-v1')
    expect(mocks.listSearchSets).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Close Skill dialog' }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove Skill' }))
    expect(mocks.selectSkill).toHaveBeenCalledWith(null)
    expect(mocks.send).not.toHaveBeenCalled()
  })

  it('changes the Skill in place and keeps the picker open on failure', async () => {
    mocks.activeSkill = { uuid: 'award-skill', title: 'Award Review', version: 'v1', instructions: 'Review dates.' }
    mocks.listSearchSets.mockResolvedValue([
      { uuid: 'replacement', title: 'Budget Review', set_type: 'prompt' },
      { uuid: 'extraction', title: 'Extract costs', set_type: 'extraction' },
    ])
    mocks.selectSkill.mockResolvedValueOnce(false).mockResolvedValueOnce(true)
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: 'Change Skill' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Budget Review' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your current Skill is still selected')
    expect(screen.queryByRole('button', { name: 'Extract costs' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Budget Review' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(mocks.selectSkill).toHaveBeenCalledWith('replacement')
    expect(mocks.send).not.toHaveBeenCalled()
  })

  it('shares a Skill-only setup without exposing its saved instructions', async () => {
    mocks.activeSkill = { uuid: 'award-skill', title: 'Award Review', version: 'v1', instructions: 'Private instructions' }
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: 'Share chat setup' }))
    expect(writeText).toHaveBeenCalledOnce()
    expect(new URL(writeText.mock.calls[0][0]).search).toBe('?skill=award-skill')
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

it('keeps expanded reasoning mounted when the first response text arrives', () => {
  mocks.isStreaming = true
  mocks.thinkingContent = 'Reviewing the request'
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const { rerender } = render(<QueryClientProvider client={client}><ChatPanel /></QueryClientProvider>)
  fireEvent.click(screen.getByRole('button', { name: 'Expand thinking' }))
  const disclosure = screen.getByRole('button', { name: 'Collapse thinking' })
  mocks.segments = [{ kind: 'text', content: 'Here is the response.' }]
  rerender(<QueryClientProvider client={client}><ChatPanel /></QueryClientProvider>)
  expect(screen.getByRole('button', { name: 'Collapse thinking' })).toBe(disclosure)
  expect(screen.getByText('Reviewing the request')).toBeVisible()
  expect(screen.getByText('Here is the response.')).toBeVisible()
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


describe('Page preparation progress in the conversation', () => {
  it.each(['create_html_artifact', 'revise_html_artifact'])('keeps %s progress visible through the preamble, reasoning, execution and preview', toolName => {
    mocks.isStreaming = true
    mocks.thinkingContent = 'Earlier reasoning'
    mocks.streamingContent = "I'm preparing the page."
    mocks.segments = [{ kind: 'text', content: mocks.streamingContent }]
    mocks.activity = { phase: 'writing' }
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const view = render(<QueryClientProvider client={client}><ChatPanel /></QueryClientProvider>)
    const rerender = () => view.rerender(<QueryClientProvider client={client}><ChatPanel /></QueryClientProvider>)
    expect(screen.getByRole('status', { name: 'Assistant progress' })).toHaveTextContent('Writing your response')

    mocks.thinkingContent = 'Earlier reasoning'
    mocks.activity = { phase: 'tool_preparing', tool_name: toolName, tool_call_id: 'page' }
    rerender()
    const progress = screen.getByRole('status', { name: 'Assistant progress' })
    expect(progress).toHaveTextContent(toolName === 'create_html_artifact' ? 'Designing your page' : 'Revising your page')
    expect(progress).toHaveTextContent('0:00 elapsed')
    expect(screen.getByRole('region', { name: 'Conversation' })).toContainElement(progress)
    expect(screen.getByRole('button', { name: 'Expand thinking' })).toHaveTextContent('Reasoning')
    expect(screen.queryByTitle('Page preview')).not.toBeInTheDocument()
    rerender()
    expect(screen.getByRole('status', { name: 'Assistant progress' })).toBe(progress)

    const call = { tool_name: toolName, tool_call_id: 'page', args: { title: 'Award page' } }
    mocks.activeToolCalls = [call]
    mocks.segments.push({ kind: 'tool_call', call })
    mocks.activity = { phase: 'tool_running', tool_name: toolName, tool_call_id: 'page' }
    rerender()
    expect(screen.getByText('Preparing your page preview')).toBeVisible()
    expect(screen.queryByRole('status', { name: 'Assistant progress' })).not.toBeInTheDocument()

    const result = { tool_name: toolName, tool_call_id: 'page', quality: null,
      content: { needs_confirmation: true, title: 'Award page', artifact_preview_html: '<h1>Ready</h1>' } }
    mocks.activeToolCalls = []
    mocks.toolResults = [result]
    mocks.segments.push({ kind: 'tool_result', result })
    mocks.activity = { phase: 'reviewing', tool_name: toolName }
    rerender()
    expect(screen.getByTitle('Page preview')).toBeInTheDocument()
    expect(screen.getByText('Ready for your review')).toBeVisible()
    expect(screen.queryByText(/elapsed/)).not.toBeInTheDocument()
    expect(screen.queryByText('Preparing your page preview')).not.toBeInTheDocument()
  })

  it.each(['stopped', 'failed'])('removes Page preparation progress when the stream is %s', outcome => {
    mocks.isStreaming = true
    mocks.activity = { phase: 'tool_preparing', tool_name: 'create_html_artifact', tool_call_id: 'page' }
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const view = render(<QueryClientProvider client={client}><ChatPanel /></QueryClientProvider>)
    expect(screen.getByRole('status', { name: 'Assistant progress' })).toHaveTextContent('Designing your page')
    mocks.isStreaming = false
    mocks.activity = null
    if (outcome === 'failed') mocks.error = 'The response was interrupted.'
    view.rerender(<QueryClientProvider client={client}><ChatPanel /></QueryClientProvider>)
    expect(screen.queryByRole('status', { name: 'Assistant progress' })).not.toBeInTheDocument()
    expect(screen.queryByText(/elapsed/)).not.toBeInTheDocument()
  })
})
