import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'

type RightTab = 'assistant' | 'library'
export type WorkspaceMode = 'chat' | 'files' | 'automations' | 'knowledge'

// ---------------------------------------------------------------------------
// 1. Navigation Context — URL-synced panels, mode, tab
// ---------------------------------------------------------------------------

interface NavigationContextValue {
  workspaceMode: WorkspaceMode
  setWorkspaceMode: (mode: WorkspaceMode) => void
  activeRightTab: RightTab
  setActiveRightTab: (tab: RightTab) => void
  openWorkflowId: string | null
  openWorkflow: (id: string) => void
  closeWorkflow: () => void
  openExtractionId: string | null
  openExtraction: (uuid: string, initialResults?: Record<string, string>) => void
  closeExtraction: () => void
  consumeExtractionResults: () => Record<string, string> | null
  openAutomationId: string | null
  openAutomation: (id: string) => void
  closeAutomation: () => void
  resetToHome: () => void
}

const NavigationContext = createContext<NavigationContextValue | null>(null)

// ---------------------------------------------------------------------------
// 2. Chat State Context — conversation, KB, messages, signals
// ---------------------------------------------------------------------------

interface ChatStateContextValue {
  loadConversationId: string | null
  setLoadConversationId: (id: string | null) => void
  newChatSignal: number
  triggerNewChat: () => void
  pendingChatMessage: string | null
  sendChatMessage: (message: string) => void
  clearPendingChatMessage: () => void
  activeKBUuid: string | null
  activeKBTitle: string | null
  activateKB: (uuid: string, title: string) => void
  deactivateKB: () => void
  processingDoc: { title: string; status: string | null } | null
  setProcessingDoc: (doc: { title: string; status: string | null } | null) => void
}

const ChatStateContext = createContext<ChatStateContextValue | null>(null)

// ---------------------------------------------------------------------------
// 3. UI State Context — selections, layout, highlights
// ---------------------------------------------------------------------------

interface UIStateContextValue {
  selectedDocUuids: string[]
  setSelectedDocUuids: (uuids: string[]) => void
  selectedFolderUuids: string[]
  setSelectedFolderUuids: (uuids: string[]) => void
  railDocked: boolean
  toggleRailDocked: () => void
  panelSplit: number
  setPanelSplit: (pct: number, skipPersist?: boolean) => void
  highlightTerms: string[]
  setHighlightTerms: (terms: string[]) => void
  activitySignal: number
  bumpActivitySignal: () => void
  viewDocumentRequest: { uuid: string; title: string } | null
  viewDocument: (uuid: string, title: string) => void
  clearViewDocumentRequest: () => void
}

const UIStateContext = createContext<UIStateContextValue | null>(null)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

type WorkspaceSearchState = {
  mode: WorkspaceMode | undefined
  tab: RightTab | undefined
  workflow: string | undefined
  extraction: string | undefined
  automation: string | undefined
  kb: string | undefined
}

function emptyWorkspaceSearch(): WorkspaceSearchState {
  return {
    mode: undefined,
    tab: undefined,
    workflow: undefined,
    extraction: undefined,
    automation: undefined,
    kb: undefined,
  }
}

// ---------------------------------------------------------------------------
// Provider — wraps all three contexts
// ---------------------------------------------------------------------------

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate({ from: '/' })
  const search = useSearch({ from: '/' })

  // ── URL-derived state ───────────────────────────────────────────────────
  const workspaceMode: WorkspaceMode =
    search.mode ??
    getStoredString('workspace:mode', 'chat', ['chat', 'files', 'automations', 'knowledge'])

  const openWorkflowId: string | null = search.workflow ?? null
  const openExtractionId: string | null = search.extraction ?? null
  const openAutomationId: string | null = search.automation ?? null
  const activeRightTab: RightTab = search.tab ?? 'assistant'

  // ── Ephemeral React state ───────────────────────────────────────────────
  const [selectedDocUuids, setSelectedDocUuids] = useState<string[]>([])
  const [selectedFolderUuids, setSelectedFolderUuids] = useState<string[]>([])
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
  const pendingExtractionResultsRef = useRef<Record<string, string> | null>(null)

  const updateSearch = useCallback(
    (updater: (prev: WorkspaceSearchState) => WorkspaceSearchState) => {
      navigate({
        search: (prev) => updater({ ...emptyWorkspaceSearch(), ...prev }),
        replace: true,
      })
    },
    [navigate],
  )

  // ── Navigation callbacks ────────────────────────────────────────────────

  const setWorkspaceMode = useCallback((mode: WorkspaceMode) => {
    localStorage.setItem('workspace:mode', mode)
    updateSearch((prev) => ({ ...prev, mode: mode === 'chat' ? undefined : mode }))
  }, [updateSearch])

  const setActiveRightTab = useCallback((tab: RightTab) => {
    updateSearch((prev) => ({ ...prev, tab: tab === 'assistant' ? undefined : tab }))
  }, [updateSearch])

  const openWorkflow = useCallback((id: string) => {
    updateSearch((prev) => ({ ...prev, workflow: id, extraction: undefined, automation: undefined }))
  }, [updateSearch])

  const closeWorkflow = useCallback(() => {
    updateSearch((prev) => ({ ...prev, workflow: undefined }))
  }, [updateSearch])

  const openExtraction = useCallback((uuid: string, initialResults?: Record<string, string>) => {
    pendingExtractionResultsRef.current = initialResults ?? null
    updateSearch((prev) => ({ ...prev, extraction: uuid, workflow: undefined, automation: undefined }))
  }, [updateSearch])

  const consumeExtractionResults = useCallback((): Record<string, string> | null => {
    const r = pendingExtractionResultsRef.current
    pendingExtractionResultsRef.current = null
    return r
  }, [])

  const closeExtraction = useCallback(() => {
    updateSearch((prev) => ({ ...prev, extraction: undefined }))
  }, [updateSearch])

  const openAutomation = useCallback((id: string) => {
    updateSearch((prev) => ({ ...prev, automation: id, workflow: undefined, extraction: undefined }))
  }, [updateSearch])

  const closeAutomation = useCallback(() => {
    updateSearch((prev) => ({ ...prev, automation: undefined }))
  }, [updateSearch])

  const resetToHome = useCallback(() => {
    updateSearch(() => emptyWorkspaceSearch())
    localStorage.setItem('workspace:mode', 'chat')
    setNewChatSignal(prev => prev + 1)
    setLoadConversationId(null)
    setPendingChatMessage(null)
    setHighlightTerms([])
    setActiveKBUuid(null)
    setActiveKBTitle(null)
  }, [updateSearch])

  // ── Chat callbacks ──────────────────────────────────────────────────────

  const triggerNewChat = useCallback(() => {
    setNewChatSignal(prev => prev + 1)
    updateSearch((prev) => ({ ...prev, workflow: undefined, extraction: undefined, automation: undefined, tab: undefined }))
  }, [updateSearch])

  const sendChatMessage = useCallback((message: string) => {
    updateSearch((prev) => ({ ...prev, workflow: undefined, extraction: undefined, automation: undefined, tab: undefined }))
    setPendingChatMessage(message)
  }, [updateSearch])

  const clearPendingChatMessage = useCallback(() => {
    setPendingChatMessage(null)
  }, [])

  const activateKB = useCallback((uuid: string, title: string) => {
    setActiveKBUuid(uuid)
    setActiveKBTitle(title)
    setNewChatSignal(prev => prev + 1)
    localStorage.setItem('workspace:mode', 'chat')
    updateSearch((prev) => ({ ...prev, mode: undefined, workflow: undefined, extraction: undefined, automation: undefined, tab: undefined }))
  }, [updateSearch])

  const deactivateKB = useCallback(() => {
    setActiveKBUuid(null)
    setActiveKBTitle(null)
  }, [])

  // Activate a knowledge base from URL param (e.g. /?kb=<uuid>)
  useEffect(() => {
    const kbParam = search.kb
    if (!kbParam) return
    // Clear the param from the URL, then activate
    import('../api/knowledge').then(({ getKnowledgeBase }) => {
      getKnowledgeBase(kbParam)
        .then((kb) => {
          setActiveKBUuid(kbParam)
          setActiveKBTitle(kb.title)
          localStorage.setItem('workspace:mode', 'chat')
          navigate({
            search: (prev) => ({ ...emptyWorkspaceSearch(), ...prev, kb: undefined, mode: undefined, workflow: undefined, extraction: undefined, automation: undefined, tab: undefined }),
            replace: true,
          })
        })
        .catch(() => {
          // KB not found or not accessible — just clear the param
          navigate({
            search: (prev) => ({ ...emptyWorkspaceSearch(), ...prev, kb: undefined }),
            replace: true,
          })
        })
    })
  }, [search.kb, navigate])

  // ── UI callbacks ────────────────────────────────────────────────────────

  const bumpActivitySignal = useCallback(() => {
    setActivitySignal(prev => prev + 1)
  }, [])

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

  const viewDocument = useCallback((uuid: string, title: string) => {
    setViewDocumentRequest({ uuid, title })
  }, [])

  const clearViewDocumentRequest = useCallback(() => {
    setViewDocumentRequest(null)
  }, [])

  // ── Memoized context values ─────────────────────────────────────────────

  const navValue = useMemo<NavigationContextValue>(() => ({
    workspaceMode, setWorkspaceMode,
    activeRightTab, setActiveRightTab,
    openWorkflowId, openWorkflow, closeWorkflow,
    openExtractionId, openExtraction, closeExtraction,
    consumeExtractionResults,
    openAutomationId, openAutomation, closeAutomation,
    resetToHome,
  }), [
    workspaceMode, setWorkspaceMode,
    activeRightTab, setActiveRightTab,
    openWorkflowId, openWorkflow, closeWorkflow,
    openExtractionId, openExtraction, closeExtraction,
    consumeExtractionResults,
    openAutomationId, openAutomation, closeAutomation,
    resetToHome,
  ])

  const chatValue = useMemo<ChatStateContextValue>(() => ({
    loadConversationId, setLoadConversationId,
    newChatSignal, triggerNewChat,
    pendingChatMessage, sendChatMessage, clearPendingChatMessage,
    activeKBUuid, activeKBTitle, activateKB, deactivateKB,
    processingDoc, setProcessingDoc,
  }), [
    loadConversationId, newChatSignal, triggerNewChat,
    pendingChatMessage, sendChatMessage, clearPendingChatMessage,
    activeKBUuid, activeKBTitle, activateKB, deactivateKB,
    processingDoc,
  ])

  const uiValue = useMemo<UIStateContextValue>(() => ({
    selectedDocUuids, setSelectedDocUuids,
    selectedFolderUuids, setSelectedFolderUuids,
    railDocked, toggleRailDocked,
    panelSplit, setPanelSplit,
    highlightTerms, setHighlightTerms,
    activitySignal, bumpActivitySignal,
    viewDocumentRequest, viewDocument, clearViewDocumentRequest,
  }), [
    selectedDocUuids, selectedFolderUuids,
    railDocked, toggleRailDocked,
    panelSplit, setPanelSplit,
    highlightTerms, activitySignal, bumpActivitySignal,
    viewDocumentRequest, viewDocument, clearViewDocumentRequest,
  ])

  return (
    <NavigationContext.Provider value={navValue}>
      <ChatStateContext.Provider value={chatValue}>
        <UIStateContext.Provider value={uiValue}>
          {children}
        </UIStateContext.Provider>
      </ChatStateContext.Provider>
    </NavigationContext.Provider>
  )
}

// ---------------------------------------------------------------------------
// Focused hooks — use these for minimal rerenders
// ---------------------------------------------------------------------------

export function useWorkspaceNavigation() {
  const ctx = useContext(NavigationContext)
  if (!ctx) throw new Error('useWorkspaceNavigation must be used within WorkspaceProvider')
  return ctx
}

export function useWorkspaceChatState() {
  const ctx = useContext(ChatStateContext)
  if (!ctx) throw new Error('useWorkspaceChatState must be used within WorkspaceProvider')
  return ctx
}

export function useWorkspaceUI() {
  const ctx = useContext(UIStateContext)
  if (!ctx) throw new Error('useWorkspaceUI must be used within WorkspaceProvider')
  return ctx
}

// ---------------------------------------------------------------------------
// Backwards-compatible facade — combines all three contexts
// Components can incrementally migrate to focused hooks above.
// ---------------------------------------------------------------------------

export function useWorkspace() {
  const nav = useContext(NavigationContext)
  const chat = useContext(ChatStateContext)
  const ui = useContext(UIStateContext)
  if (!nav || !chat || !ui) throw new Error('useWorkspace must be used within WorkspaceProvider')
  return { ...nav, ...chat, ...ui }
}

export function useOptionalWorkspace() {
  const nav = useContext(NavigationContext)
  const chat = useContext(ChatStateContext)
  const ui = useContext(UIStateContext)
  if (!nav || !chat || !ui) return null
  return { ...nav, ...chat, ...ui }
}
