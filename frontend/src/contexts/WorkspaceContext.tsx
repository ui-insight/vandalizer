import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'

type RightTab = 'assistant' | 'library'
export type WorkspaceMode = 'chat' | 'files' | 'automations' | 'knowledge'

interface WorkspaceContextValue {
  workspaceMode: WorkspaceMode
  setWorkspaceMode: (mode: WorkspaceMode) => void
  selectedDocUuids: string[]
  setSelectedDocUuids: (uuids: string[]) => void
  activeRightTab: RightTab
  setActiveRightTab: (tab: RightTab) => void
  railDocked: boolean
  toggleRailDocked: () => void
  panelSplit: number
  setPanelSplit: (pct: number, skipPersist?: boolean) => void
  /** Load a conversation by its activity ID in the assistant tab */
  loadConversationId: string | null
  setLoadConversationId: (id: string | null) => void
  /** Incremented to signal a new-chat reset */
  newChatSignal: number
  triggerNewChat: () => void
  /** Workflow open in the right pane (replaces tabs when set) */
  openWorkflowId: string | null
  openWorkflow: (id: string) => void
  closeWorkflow: () => void
  /** Extraction (SearchSet) open in the right pane by UUID */
  openExtractionId: string | null
  openExtraction: (uuid: string) => void
  closeExtraction: () => void
  /** Automation open in the right pane */
  openAutomationId: string | null
  openAutomation: (id: string) => void
  closeAutomation: () => void
  /** Pending message to send in the assistant chat */
  pendingChatMessage: string | null
  sendChatMessage: (message: string) => void
  clearPendingChatMessage: () => void
  /** Terms to highlight in the PDF viewer */
  highlightTerms: string[]
  setHighlightTerms: (terms: string[]) => void
  /** Bumped to signal the activity rail to re-fetch */
  activitySignal: number
  bumpActivitySignal: () => void
  /** Track document currently being processed (shown in chat panel) */
  processingDoc: { title: string; status: string | null } | null
  setProcessingDoc: (doc: { title: string; status: string | null } | null) => void
  /** Active knowledge base for chat */
  activeKBUuid: string | null
  activeKBTitle: string | null
  activateKB: (uuid: string, title: string) => void
  deactivateKB: () => void
  /** Reset workspace to default home state */
  resetToHome: () => void
  /** Request the left panel to view a specific document */
  viewDocumentRequest: { uuid: string; title: string } | null
  viewDocument: (uuid: string, title: string) => void
  clearViewDocumentRequest: () => void
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null)

function getStoredBool(key: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(key)
    if (v === null) return fallback
    return v === 'true'
  } catch {
    return fallback
  }
}

function getStoredString<T extends string>(key: string, fallback: T, valid: T[]): T {
  try {
    const v = localStorage.getItem(key)
    if (v !== null && valid.includes(v as T)) return v as T
    return fallback
  } catch {
    return fallback
  }
}

function getStoredNumber(key: string, fallback: number): number {
  try {
    const v = localStorage.getItem(key)
    if (v === null) return fallback
    const n = parseFloat(v)
    return isNaN(n) ? fallback : n
  } catch {
    return fallback
  }
}

type NavSearch = (prev: Record<string, unknown>) => Record<string, unknown>

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const search = useSearch({ from: '/' })

  // ── URL-derived state ─────────────────────────────────────────────────────
  // These values live in the URL and are reactive via useSearch.
  // Defaults: mode falls back to localStorage, tab/editors default to none.

  const workspaceMode: WorkspaceMode =
    search.mode ??
    getStoredString('workspace:mode', 'chat', ['chat', 'files', 'automations', 'knowledge'])

  const openWorkflowId: string | null = search.workflow ?? null
  const openExtractionId: string | null = search.extraction ?? null
  const openAutomationId: string | null = search.automation ?? null
  const activeRightTab: RightTab = search.tab ?? 'assistant'

  // ── Pure React state (ephemeral / not URL-worthy) ─────────────────────────
  const [selectedDocUuids, setSelectedDocUuids] = useState<string[]>([])
  const [railDocked, setRailDocked] = useState(() => getStoredBool('workspace:railDocked', false))
  const [panelSplit, _setPanelSplit] = useState(() => getStoredNumber('workspace:panelSplit', 60))
  const [loadConversationId, setLoadConversationId] = useState<string | null>(null)
  const [newChatSignal, setNewChatSignal] = useState(0)
  const [pendingChatMessage, setPendingChatMessage] = useState<string | null>(null)
  const [highlightTerms, setHighlightTerms] = useState<string[]>([])
  const [activitySignal, setActivitySignal] = useState(0)
  const [processingDoc, setProcessingDoc] = useState<{ title: string; status: string | null } | null>(null)
  const [activeKBUuid, setActiveKBUuid] = useState<string | null>(null)
  const [activeKBTitle, setActiveKBTitle] = useState<string | null>(null)
  const [viewDocumentRequest, setViewDocumentRequest] = useState<{ uuid: string; title: string } | null>(null)

  // ── URL-updating setters ──────────────────────────────────────────────────

  const setWorkspaceMode = useCallback((mode: WorkspaceMode) => {
    localStorage.setItem('workspace:mode', mode)
    navigate({ search: ((prev: Record<string, unknown>) => ({ ...prev, mode: mode === 'chat' ? undefined : mode })) as NavSearch, replace: true })
  }, [navigate])

  const setActiveRightTab = useCallback((tab: RightTab) => {
    navigate({ search: ((prev: Record<string, unknown>) => ({ ...prev, tab: tab === 'assistant' ? undefined : tab })) as NavSearch, replace: true })
  }, [navigate])

  const openWorkflow = useCallback((id: string) => {
    navigate({ search: ((prev: Record<string, unknown>) => ({ ...prev, workflow: id, extraction: undefined, automation: undefined })) as NavSearch, replace: true })
  }, [navigate])

  const closeWorkflow = useCallback(() => {
    navigate({ search: ((prev: Record<string, unknown>) => ({ ...prev, workflow: undefined })) as NavSearch, replace: true })
  }, [navigate])

  const openExtraction = useCallback((uuid: string) => {
    navigate({ search: ((prev: Record<string, unknown>) => ({ ...prev, extraction: uuid, workflow: undefined, automation: undefined })) as NavSearch, replace: true })
  }, [navigate])

  const closeExtraction = useCallback(() => {
    navigate({ search: ((prev: Record<string, unknown>) => ({ ...prev, extraction: undefined })) as NavSearch, replace: true })
  }, [navigate])

  const openAutomation = useCallback((id: string) => {
    navigate({ search: ((prev: Record<string, unknown>) => ({ ...prev, automation: id, workflow: undefined, extraction: undefined })) as NavSearch, replace: true })
  }, [navigate])

  const closeAutomation = useCallback(() => {
    navigate({ search: ((prev: Record<string, unknown>) => ({ ...prev, automation: undefined })) as NavSearch, replace: true })
  }, [navigate])

  const bumpActivitySignal = useCallback(() => {
    setActivitySignal(prev => prev + 1)
  }, [])

  const sendChatMessage = useCallback((message: string) => {
    navigate({ search: ((prev: Record<string, unknown>) => ({ ...prev, workflow: undefined, extraction: undefined, automation: undefined, tab: undefined })) as NavSearch, replace: true })
    setPendingChatMessage(message)
  }, [navigate])

  const clearPendingChatMessage = useCallback(() => {
    setPendingChatMessage(null)
  }, [])

  const triggerNewChat = useCallback(() => {
    setNewChatSignal(prev => prev + 1)
    navigate({ search: ((prev: Record<string, unknown>) => ({ ...prev, workflow: undefined, extraction: undefined, automation: undefined, tab: undefined })) as NavSearch, replace: true })
  }, [navigate])

  const activateKB = useCallback((uuid: string, title: string) => {
    setActiveKBUuid(uuid)
    setActiveKBTitle(title)
    localStorage.setItem('workspace:mode', 'chat')
    navigate({ search: ((prev: Record<string, unknown>) => ({ ...prev, mode: undefined, workflow: undefined, extraction: undefined, automation: undefined, tab: undefined })) as NavSearch, replace: true })
  }, [navigate])

  const deactivateKB = useCallback(() => {
    setActiveKBUuid(null)
    setActiveKBTitle(null)
  }, [])

  const viewDocument = useCallback((uuid: string, title: string) => {
    setViewDocumentRequest({ uuid, title })
  }, [])

  const clearViewDocumentRequest = useCallback(() => {
    setViewDocumentRequest(null)
  }, [])

  const resetToHome = useCallback(() => {
    navigate({ search: {}, replace: true })
    localStorage.setItem('workspace:mode', 'chat')
    setNewChatSignal(prev => prev + 1)
    setLoadConversationId(null)
    setPendingChatMessage(null)
    setHighlightTerms([])
    setActiveKBUuid(null)
    setActiveKBTitle(null)
  }, [navigate])

  const toggleRailDocked = useCallback(() => {
    setRailDocked(prev => {
      const next = !prev
      localStorage.setItem('workspace:railDocked', String(next))
      return next
    })
  }, [])

  const setPanelSplit = useCallback((pct: number, skipPersist?: boolean) => {
    const clamped = Math.min(80, Math.max(20, pct))
    _setPanelSplit(clamped)
    if (!skipPersist) {
      localStorage.setItem('workspace:panelSplit', String(clamped))
    }
  }, [])

  return (
    <WorkspaceContext.Provider
      value={{
        workspaceMode,
        setWorkspaceMode,
        selectedDocUuids,
        setSelectedDocUuids,
        activeRightTab,
        setActiveRightTab,
        railDocked,
        toggleRailDocked,
        panelSplit,
        setPanelSplit,
        loadConversationId,
        setLoadConversationId,
        newChatSignal,
        triggerNewChat,
        openWorkflowId,
        openWorkflow,
        closeWorkflow,
        openExtractionId,
        openExtraction,
        closeExtraction,
        openAutomationId,
        openAutomation,
        closeAutomation,
        pendingChatMessage,
        sendChatMessage,
        clearPendingChatMessage,
        highlightTerms,
        setHighlightTerms,
        activitySignal,
        bumpActivitySignal,
        processingDoc,
        setProcessingDoc,
        activeKBUuid,
        activeKBTitle,
        activateKB,
        deactivateKB,
        resetToHome,
        viewDocumentRequest,
        viewDocument,
        clearViewDocumentRequest,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  )
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext)
  if (!ctx) throw new Error('useWorkspace must be used within WorkspaceProvider')
  return ctx
}

export function useOptionalWorkspace() {
  return useContext(WorkspaceContext)
}
