import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

type RightTab = 'assistant' | 'library'

interface WorkspaceContextValue {
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

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [selectedDocUuids, setSelectedDocUuids] = useState<string[]>([])
  const [activeRightTab, setActiveRightTab] = useState<RightTab>('assistant')
  const [railDocked, setRailDocked] = useState(() => getStoredBool('workspace:railDocked', false))
  const [panelSplit, _setPanelSplit] = useState(() => getStoredNumber('workspace:panelSplit', 60))
  const [loadConversationId, setLoadConversationId] = useState<string | null>(null)
  const [newChatSignal, setNewChatSignal] = useState(0)
  const [openWorkflowId, setOpenWorkflowId] = useState<string | null>(null)
  const [openExtractionId, setOpenExtractionId] = useState<string | null>(null)
  const [pendingChatMessage, setPendingChatMessage] = useState<string | null>(null)
  const [highlightTerms, setHighlightTerms] = useState<string[]>([])
  const [activitySignal, setActivitySignal] = useState(0)
  const [processingDoc, setProcessingDoc] = useState<{ title: string; status: string | null } | null>(null)

  const bumpActivitySignal = useCallback(() => {
    setActivitySignal(prev => prev + 1)
  }, [])

  const sendChatMessage = useCallback((message: string) => {
    setOpenWorkflowId(null)
    setOpenExtractionId(null)
    setActiveRightTab('assistant')
    setPendingChatMessage(message)
  }, [])

  const clearPendingChatMessage = useCallback(() => {
    setPendingChatMessage(null)
  }, [])

  const triggerNewChat = useCallback(() => {
    setNewChatSignal(prev => prev + 1)
    setOpenWorkflowId(null)
    setOpenExtractionId(null)
    setActiveRightTab('assistant')
  }, [])

  const openWorkflow = useCallback((id: string) => {
    setOpenExtractionId(null)
    setOpenWorkflowId(id)
  }, [])

  const closeWorkflow = useCallback(() => {
    setOpenWorkflowId(null)
  }, [])

  const openExtraction = useCallback((uuid: string) => {
    setOpenWorkflowId(null)
    setOpenExtractionId(uuid)
  }, [])

  const closeExtraction = useCallback(() => {
    setOpenExtractionId(null)
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

  return (
    <WorkspaceContext.Provider
      value={{
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
        pendingChatMessage,
        sendChatMessage,
        clearPendingChatMessage,
        highlightTerms,
        setHighlightTerms,
        activitySignal,
        bumpActivitySignal,
        processingDoc,
        setProcessingDoc,
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
