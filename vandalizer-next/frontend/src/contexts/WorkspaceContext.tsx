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
  setPanelSplit: (pct: number) => void
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

  const setPanelSplit = useCallback((pct: number) => {
    const clamped = Math.min(80, Math.max(20, pct))
    _setPanelSplit(clamped)
    localStorage.setItem('workspace:panelSplit', String(clamped))
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
