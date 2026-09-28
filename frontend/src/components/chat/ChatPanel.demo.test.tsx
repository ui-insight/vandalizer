import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChatPanel } from './ChatPanel'
import { pollStatus } from '../../api/documents'

const mocks = vi.hoisted(() => ({
  send: vi.fn(),
  uploading: false,
  workspace: {
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
  messages: [], segments: [], queuedMessages: [], planTasks: [], contextNotices: [],
  isStreaming: false, contextTokens: 0, send: mocks.send,
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

function renderPanel() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ChatPanel /></QueryClientProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.uploading = false
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
