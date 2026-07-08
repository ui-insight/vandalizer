import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import type { VerificationSession } from '../api/verificationSessions'
import { useTeams } from '../hooks/useTeams'

type RightTab = 'assistant' | 'library'
export type WorkspaceMode = 'chat' | 'files' | 'automations' | 'knowledge' | 'projects'

export interface VerificationCompletion {
  sessionId: string
  extractionSetUuid: string
  documentTitle: string
  testCaseUuid: string | null
  outcome: 'finalized' | 'cancelled'
  approvedCount: number
  correctedCount: number
  skippedCount: number
}

// ---------------------------------------------------------------------------
// 1. Navigation Context — URL-synced panels, mode, tab
// ---------------------------------------------------------------------------

interface NavigationContextValue {
  workspaceMode: WorkspaceMode
  setWorkspaceMode: (mode: WorkspaceMode) => void
  activeRightTab: RightTab
  setActiveRightTab: (tab: RightTab) => void
  openWorkflowId: string | null
  openWorkflowShareToken: string | null
  openWorkflow: (id: string, sessionId?: string) => void
  closeWorkflow: () => void
  consumeWorkflowSession: () => string | null
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

export interface PendingChatMessage {
  message: string
  documentUuids?: string[]
  folderUuids?: string[]
}

interface ChatStateContextValue {
  loadConversationId: string | null
  setLoadConversationId: (id: string | null) => void
  // UUID of the conversation currently displayed in ChatPanel. Surfaced
  // upward so other UI (e.g. ActivityRail delete) can tell whether a
  // deleted activity is the one the user is looking at right now.
  currentConversationUuid: string | null
  setCurrentConversationUuid: (uuid: string | null) => void
  newChatSignal: number
  triggerNewChat: () => void
  // Bumped to ask the ChatPanel to reveal itself and focus the composer
  // (e.g. the file browser's "Ask about folder" action) without starting a
  // new conversation.
  focusChatSignal: number
  focusChat: () => void
  pendingChatMessage: PendingChatMessage | null
  sendChatMessage: (
    message: string,
    options?: { documentUuids?: string[]; folderUuids?: string[] },
  ) => void
  clearPendingChatMessage: () => void
  activeKBUuid: string | null
  activeKBTitle: string | null
  activateKB: (uuid: string, title: string) => void
  deactivateKB: () => void
  // Project scope — the whole workspace (files, chat, …) re-scoped to one project.
  activeProjectUuid: string | null
  activeProjectTitle: string | null
  activeProjectRootFolder: string | null
  activeProjectTeamId: string | null
  activeProjectRole: string | null // owner|editor|viewer — gates mutating UI
  activateProject: (uuid: string, title: string) => void
  deactivateProject: () => void
  // Re-pull the active project's metadata (title/role/team) into the context
  // bar after an in-workspace edit (rename, share, make-personal) — without
  // resetting the chat the way activateProject does.
  refreshActiveProject: () => void
  processingDoc: { title: string; status: string | null } | null
  setProcessingDoc: (doc: { title: string; status: string | null } | null) => void
  // Subset of selectedDocUuids that are still being processed by the upload
  // pipeline. Populated by the file browser so the chat banner can avoid
  // claiming "ready for analysis" while OCR/indexing is still running.
  selectedDocsProcessing: Array<{ uuid: string; title: string; status: string | null }>
  setSelectedDocsProcessing: (docs: Array<{ uuid: string; title: string; status: string | null }>) => void
}

const ChatStateContext = createContext<ChatStateContextValue | null>(null)

// ---------------------------------------------------------------------------
// 3. UI State Context — selections, layout, highlights
// ---------------------------------------------------------------------------

interface UIStateContextValue {
  selectedDocUuids: string[]
  setSelectedDocUuids: (uuids: string[]) => void
  selectedDocNames: Record<string, string>
  setSelectedDocNames: (names: Record<string, string>) => void
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
  verificationSession: VerificationSession | null
  setVerificationSession: (s: VerificationSession | null) => void
  verificationCompletion: VerificationCompletion | null
  setVerificationCompletion: (c: VerificationCompletion | null) => void
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

/** Read a free-form stored value (e.g. an active project/KB uuid). */
function getStoredRaw(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

/** Persist (or, with null, clear) a free-form stored value. */
function setStoredRaw(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    /* storage unavailable (private mode / quota) — scope just won't persist */
  }
}

const PROJECT_STORAGE_KEY = 'workspace:project'
const KB_STORAGE_KEY = 'workspace:kb'

type WorkspaceSearchState = {
  mode: WorkspaceMode | undefined
  tab: RightTab | undefined
  workflow: string | undefined
  workflow_share_token: string | undefined
  extraction: string | undefined
  automation: string | undefined
  kb: string | undefined
  project: string | undefined
}

function emptyWorkspaceSearch(): WorkspaceSearchState {
  return {
    mode: undefined,
    tab: undefined,
    workflow: undefined,
    workflow_share_token: undefined,
    extraction: undefined,
    automation: undefined,
    kb: undefined,
    project: undefined,
  }
}

// ---------------------------------------------------------------------------
// Provider — wraps all three contexts
// ---------------------------------------------------------------------------

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate({ from: '/' })
  const search = useSearch({ from: '/' })
  const { currentTeam } = useTeams()

  // ── URL-derived state ───────────────────────────────────────────────────
  const workspaceMode: WorkspaceMode =
    search.mode ??
    getStoredString('workspace:mode', 'chat', ['chat', 'files', 'automations', 'knowledge', 'projects'])

  const openWorkflowId: string | null = search.workflow ?? null
  const openWorkflowShareToken: string | null = search.workflow_share_token ?? null
  const openExtractionId: string | null = search.extraction ?? null
  const openAutomationId: string | null = search.automation ?? null
  const activeRightTab: RightTab = search.tab ?? 'assistant'

  // ── Ephemeral React state ───────────────────────────────────────────────
  const [selectedDocUuids, setSelectedDocUuids] = useState<string[]>([])
  const [selectedDocNames, setSelectedDocNames] = useState<Record<string, string>>({})
  const [selectedFolderUuids, setSelectedFolderUuids] = useState<string[]>([])
  const [railDocked, setRailDocked] = useState(() => getStoredBool('workspace:railDocked', false))
  const [panelSplit, _setPanelSplit] = useState(() => getStoredNumber('workspace:panelSplit', 60))
  const [loadConversationId, setLoadConversationId] = useState<string | null>(null)
  const [currentConversationUuid, setCurrentConversationUuid] = useState<string | null>(null)
  const [newChatSignal, setNewChatSignal] = useState(0)
  const [focusChatSignal, setFocusChatSignal] = useState(0)
  const [pendingChatMessage, setPendingChatMessage] = useState<PendingChatMessage | null>(null)
  const [highlightTerms, setHighlightTerms] = useState<string[]>([])
  const [activitySignal, setActivitySignal] = useState(0)
  const [processingDoc, setProcessingDoc] = useState<{ title: string; status: string | null } | null>(null)
  const [selectedDocsProcessing, _setSelectedDocsProcessing] = useState<Array<{ uuid: string; title: string; status: string | null }>>([])
  // Wrap the setter so consumers passing a fresh array each render don't
  // trigger needless re-renders of every chat consumer when the contents
  // are identical (this gets called on every documents poll).
  const setSelectedDocsProcessing = useCallback(
    (next: Array<{ uuid: string; title: string; status: string | null }>) => {
      _setSelectedDocsProcessing(prev => {
        if (prev.length !== next.length) return next
        for (let i = 0; i < prev.length; i++) {
          if (prev[i].uuid !== next[i].uuid || prev[i].status !== next[i].status) return next
        }
        return prev
      })
    },
    [],
  )
  const [activeKBUuid, setActiveKBUuid] = useState<string | null>(null)
  const [activeKBTitle, setActiveKBTitle] = useState<string | null>(null)
  const [activeProjectUuid, setActiveProjectUuid] = useState<string | null>(null)
  const [activeProjectTitle, setActiveProjectTitle] = useState<string | null>(null)
  const [activeProjectRootFolder, setActiveProjectRootFolder] = useState<string | null>(null)
  const [activeProjectTeamId, setActiveProjectTeamId] = useState<string | null>(null)
  const [activeProjectRole, setActiveProjectRole] = useState<string | null>(null)
  const [viewDocumentRequest, setViewDocumentRequest] = useState<{ uuid: string; title: string } | null>(null)
  const [verificationSession, setVerificationSession] = useState<VerificationSession | null>(null)
  const [verificationCompletion, setVerificationCompletion] = useState<VerificationCompletion | null>(null)
  const pendingExtractionResultsRef = useRef<Record<string, string> | null>(null)
  const pendingWorkflowSessionRef = useRef<string | null>(null)

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

  const openWorkflow = useCallback((id: string, sessionId?: string) => {
    pendingWorkflowSessionRef.current = sessionId ?? null
    updateSearch((prev) => ({
      ...prev,
      workflow: id,
      workflow_share_token: undefined,
      extraction: undefined,
      automation: undefined,
    }))
  }, [updateSearch])

  const closeWorkflow = useCallback(() => {
    pendingWorkflowSessionRef.current = null
    updateSearch((prev) => ({ ...prev, workflow: undefined, workflow_share_token: undefined }))
  }, [updateSearch])

  const consumeWorkflowSession = useCallback((): string | null => {
    const s = pendingWorkflowSessionRef.current
    pendingWorkflowSessionRef.current = null
    return s
  }, [])

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

  // Selected documents/folders live at the workspace level (not inside
  // ChatPanel), so remounting the chat on "New chat" does NOT clear them.
  // Every fresh-chat entry point must drop them explicitly, or a document
  // attached to the previous chat stays attached in the new one.
  const clearChatAttachments = useCallback(() => {
    setSelectedDocUuids([])
    setSelectedDocNames({})
    setSelectedFolderUuids([])
  }, [])

  const resetToHome = useCallback(() => {
    updateSearch(() => emptyWorkspaceSearch())
    localStorage.setItem('workspace:mode', 'chat')
    clearChatAttachments()
    setNewChatSignal(prev => prev + 1)
    setLoadConversationId(null)
    setPendingChatMessage(null)
    setHighlightTerms([])
    setStoredRaw(KB_STORAGE_KEY, null)
    setActiveKBUuid(null)
    setActiveKBTitle(null)
    setStoredRaw(PROJECT_STORAGE_KEY, null)
    setActiveProjectUuid(null)
    setActiveProjectTitle(null)
    setActiveProjectRootFolder(null)
    setActiveProjectTeamId(null)
    setActiveProjectRole(null)
  }, [updateSearch, clearChatAttachments])

  // ── Chat callbacks ──────────────────────────────────────────────────────

  const triggerNewChat = useCallback(() => {
    clearChatAttachments()
    setNewChatSignal(prev => prev + 1)
    updateSearch((prev) => ({ ...prev, workflow: undefined, extraction: undefined, automation: undefined, tab: undefined }))
  }, [updateSearch, clearChatAttachments])

  const focusChat = useCallback(() => {
    // Clear any right-panel overlay so the chat is visible, but keep the
    // current conversation intact (unlike triggerNewChat).
    updateSearch((prev) => ({ ...prev, workflow: undefined, extraction: undefined, automation: undefined, tab: undefined }))
    setFocusChatSignal(prev => prev + 1)
  }, [updateSearch])

  const sendChatMessage = useCallback((
    message: string,
    options?: { documentUuids?: string[]; folderUuids?: string[] },
  ) => {
    updateSearch((prev) => ({ ...prev, workflow: undefined, extraction: undefined, automation: undefined, tab: undefined }))
    setPendingChatMessage({
      message,
      documentUuids: options?.documentUuids,
      folderUuids: options?.folderUuids,
    })
  }, [updateSearch])

  const clearPendingChatMessage = useCallback(() => {
    setPendingChatMessage(null)
  }, [])

  const activateKB = useCallback((uuid: string, title: string) => {
    setStoredRaw(KB_STORAGE_KEY, uuid)
    setActiveKBUuid(uuid)
    setActiveKBTitle(title)
    clearChatAttachments()
    setNewChatSignal(prev => prev + 1)
    localStorage.setItem('workspace:mode', 'chat')
    updateSearch((prev) => ({ ...prev, mode: undefined, workflow: undefined, extraction: undefined, automation: undefined, tab: undefined }))
  }, [updateSearch, clearChatAttachments])

  const deactivateKB = useCallback(() => {
    setStoredRaw(KB_STORAGE_KEY, null)
    setActiveKBUuid(null)
    setActiveKBTitle(null)
  }, [])

  const activateProject = useCallback((uuid: string, title: string) => {
    // Persist the scope so a reload re-enters the project (see rehydrate effect).
    // We store only the uuid — title/role/root are re-fetched on rehydrate so a
    // renamed or re-shared project never shows stale chrome.
    setStoredRaw(PROJECT_STORAGE_KEY, uuid)
    setActiveProjectUuid(uuid)
    setActiveProjectTitle(title)
    // Entering a project starts a fresh, project-scoped chat.
    setStoredRaw(KB_STORAGE_KEY, null)
    setActiveKBUuid(null)
    setActiveKBTitle(null)
    clearChatAttachments()
    setNewChatSignal(prev => prev + 1)
    localStorage.setItem('workspace:mode', 'chat')
    updateSearch((prev) => ({ ...prev, mode: undefined, workflow: undefined, extraction: undefined, automation: undefined, tab: undefined }))
  }, [updateSearch, clearChatAttachments])

  const deactivateProject = useCallback(() => {
    setStoredRaw(PROJECT_STORAGE_KEY, null)
    setActiveProjectUuid(null)
    setActiveProjectTitle(null)
    setActiveProjectRootFolder(null)
    setActiveProjectTeamId(null)
    setActiveProjectRole(null)
  }, [])

  const refreshActiveProject = useCallback(() => {
    if (!activeProjectUuid) return
    import('../api/projects').then(({ getProject }) => {
      getProject(activeProjectUuid)
        .then((project) => {
          setActiveProjectTitle(project.title)
          setActiveProjectRootFolder(project.root_folder_uuid)
          setActiveProjectTeamId(project.team_id ?? null)
          setActiveProjectRole(project.role)
        })
        .catch(() => {})
    }).catch(() => {})
  }, [activeProjectUuid])

  // Activate a knowledge base from URL param (e.g. /?kb=<uuid>)
  useEffect(() => {
    const kbParam = search.kb
    if (!kbParam) return
    // Clear the param from the URL, then activate
    import('../api/knowledge').then(({ getKnowledgeBase }) => {
      getKnowledgeBase(kbParam)
        .then((kb) => {
          setStoredRaw(KB_STORAGE_KEY, kbParam)
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
    }).catch(() => {
      // Chunk load failure for the lazy import — don't leak an unhandled
      // rejection; clear the param so the URL doesn't keep retrying.
      navigate({
        search: (prev) => ({ ...emptyWorkspaceSearch(), ...prev, kb: undefined }),
        replace: true,
      })
    })
  }, [search.kb, navigate])

  // Activate a project scope from URL param (e.g. /?project=<uuid>)
  useEffect(() => {
    const projectParam = search.project
    if (!projectParam) return
    import('../api/projects').then(({ getProject }) => {
      getProject(projectParam)
        .then((project) => {
          setStoredRaw(PROJECT_STORAGE_KEY, projectParam)
          setActiveProjectUuid(projectParam)
          setActiveProjectTitle(project.title)
          setActiveProjectRootFolder(project.root_folder_uuid)
          setActiveProjectTeamId(project.team_id ?? null)
          setActiveProjectRole(project.role)
          setStoredRaw(KB_STORAGE_KEY, null)
          setActiveKBUuid(null)
          setActiveKBTitle(null)
          clearChatAttachments()
          setNewChatSignal(prev => prev + 1)
          // Land in whatever mode was requested (e.g. ?project=X&mode=files),
          // defaulting to chat. Viewers (shared-in PIs) are chat-only.
          const requestedMode = project.role === 'viewer' ? 'chat' : (search.mode ?? 'chat')
          localStorage.setItem('workspace:mode', requestedMode)
          navigate({
            // Preserve any editor param so a pinned tool (e.g. ?project=X&workflow=Y)
            // opens inside the scoped project rather than being wiped.
            search: () => ({
              ...emptyWorkspaceSearch(),
              mode: requestedMode === 'chat' ? undefined : requestedMode,
              workflow: project.role === 'viewer' ? undefined : search.workflow,
              extraction: project.role === 'viewer' ? undefined : search.extraction,
              automation: project.role === 'viewer' ? undefined : search.automation,
              project: undefined,
            }),
            replace: true,
          })
        })
        .catch(() => {
          navigate({
            search: (prev) => ({ ...emptyWorkspaceSearch(), ...prev, project: undefined }),
            replace: true,
          })
        })
    }).catch(() => {
      navigate({
        search: (prev) => ({ ...emptyWorkspaceSearch(), ...prev, project: undefined }),
        replace: true,
      })
    })
  }, [search.project, search.mode, navigate, clearChatAttachments])

  // Rehydrate the active project/KB scope on a fresh load (e.g. browser reload).
  // Scope lives in ephemeral React state, so without this a refresh would drop
  // it. We persist only the uuid and re-fetch here, so title/role/root are
  // always current and a deleted/revoked scope self-heals by clearing storage.
  // An inbound ?project=/?kb= deep link owns activation, so we defer to it.
  const didRehydrateScope = useRef(false)
  useEffect(() => {
    if (didRehydrateScope.current) return
    didRehydrateScope.current = true
    if (search.project || search.kb) return

    const storedProject = getStoredRaw(PROJECT_STORAGE_KEY)
    if (storedProject) {
      import('../api/projects').then(({ getProject }) => {
        getProject(storedProject)
          .then((project) => {
            setActiveProjectUuid(storedProject)
            setActiveProjectTitle(project.title)
            setActiveProjectRootFolder(project.root_folder_uuid)
            setActiveProjectTeamId(project.team_id ?? null)
            setActiveProjectRole(project.role)
          })
          .catch(() => { setStoredRaw(PROJECT_STORAGE_KEY, null) })
      }).catch(() => {})
      return
    }

    const storedKB = getStoredRaw(KB_STORAGE_KEY)
    if (storedKB) {
      import('../api/knowledge').then(({ getKnowledgeBase }) => {
        getKnowledgeBase(storedKB)
          .then((kb) => {
            setActiveKBUuid(storedKB)
            setActiveKBTitle(kb.title)
          })
          .catch(() => { setStoredRaw(KB_STORAGE_KEY, null) })
      }).catch(() => {})
    }
    // Run once on mount; search params are read for the deep-link guard only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Projects and knowledge bases are team-scoped. Switching the current team
  // (which happens live, without a reload) must drop any active scope so we
  // never leave the user pointed at a project they can no longer access.
  const prevTeamUuidRef = useRef<string | null | undefined>(undefined)
  useEffect(() => {
    const teamUuid = currentTeam?.uuid ?? null
    if (prevTeamUuidRef.current === undefined) {
      // First resolution of the current team — establish the baseline, don't
      // clear (this is the team the rehydrated scope already belongs to).
      prevTeamUuidRef.current = teamUuid
      return
    }
    if (prevTeamUuidRef.current === teamUuid) return
    prevTeamUuidRef.current = teamUuid
    setStoredRaw(PROJECT_STORAGE_KEY, null)
    setActiveProjectUuid(null)
    setActiveProjectTitle(null)
    setActiveProjectRootFolder(null)
    setActiveProjectTeamId(null)
    setActiveProjectRole(null)
    setStoredRaw(KB_STORAGE_KEY, null)
    setActiveKBUuid(null)
    setActiveKBTitle(null)
  }, [currentTeam?.uuid])

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
    openWorkflowId, openWorkflowShareToken, openWorkflow, closeWorkflow, consumeWorkflowSession,
    openExtractionId, openExtraction, closeExtraction,
    consumeExtractionResults,
    openAutomationId, openAutomation, closeAutomation,
    resetToHome,
  }), [
    workspaceMode, setWorkspaceMode,
    activeRightTab, setActiveRightTab,
    openWorkflowId, openWorkflowShareToken, openWorkflow, closeWorkflow, consumeWorkflowSession,
    openExtractionId, openExtraction, closeExtraction,
    consumeExtractionResults,
    openAutomationId, openAutomation, closeAutomation,
    resetToHome,
  ])

  const chatValue = useMemo<ChatStateContextValue>(() => ({
    loadConversationId, setLoadConversationId,
    currentConversationUuid, setCurrentConversationUuid,
    newChatSignal, triggerNewChat,
    focusChatSignal, focusChat,
    pendingChatMessage, sendChatMessage, clearPendingChatMessage,
    activeKBUuid, activeKBTitle, activateKB, deactivateKB,
    activeProjectUuid, activeProjectTitle, activeProjectRootFolder, activeProjectTeamId, activeProjectRole, activateProject, deactivateProject, refreshActiveProject,
    processingDoc, setProcessingDoc,
    selectedDocsProcessing, setSelectedDocsProcessing,
  }), [
    loadConversationId, currentConversationUuid,
    newChatSignal, triggerNewChat,
    focusChatSignal, focusChat,
    pendingChatMessage, sendChatMessage, clearPendingChatMessage,
    activeKBUuid, activeKBTitle, activateKB, deactivateKB,
    activeProjectUuid, activeProjectTitle, activeProjectRootFolder, activeProjectTeamId, activeProjectRole, activateProject, deactivateProject, refreshActiveProject,
    processingDoc,
    selectedDocsProcessing, setSelectedDocsProcessing,
  ])

  const uiValue = useMemo<UIStateContextValue>(() => ({
    selectedDocUuids, setSelectedDocUuids,
    selectedDocNames, setSelectedDocNames,
    selectedFolderUuids, setSelectedFolderUuids,
    railDocked, toggleRailDocked,
    panelSplit, setPanelSplit,
    highlightTerms, setHighlightTerms,
    activitySignal, bumpActivitySignal,
    viewDocumentRequest, viewDocument, clearViewDocumentRequest,
    verificationSession, setVerificationSession,
    verificationCompletion, setVerificationCompletion,
  }), [
    selectedDocUuids, selectedDocNames, selectedFolderUuids,
    railDocked, toggleRailDocked,
    panelSplit, setPanelSplit,
    highlightTerms, activitySignal, bumpActivitySignal,
    viewDocumentRequest, viewDocument, clearViewDocumentRequest,
    verificationSession, verificationCompletion,
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
