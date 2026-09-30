import { useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react'
import { ArrowLeft, FileText, Link2, Search, X } from 'lucide-react'
import { FileBrowser } from '../files/FileBrowser'
import type { ContentMatch } from '../files/FileBrowser'
import { DocumentViewer } from '../files/DocumentViewer'
import { DocumentUsageDialog } from '../files/DocumentUsageDialog'
import { RawTextModal } from '../files/RawTextModal'
import { VerificationNavBar } from '../files/VerificationNavBar'
import { ItemPickerModal } from './ItemPickerModal'
import { KBPickerModal } from '../files/KBPickerModal'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useTeams } from '../../hooks/useTeams'
import { useToast } from '../../contexts/ToastContext'
import { pollStatus, searchDocuments } from '../../api/documents'
import { getVerificationSession } from '../../api/verificationSessions'
import { runWorkflow } from '../../api/workflows'
import { addDocumentsToKB } from '../../api/knowledge'
import type { Folder } from '../../types/document'

export function LeftPanel() {
  const {
    selectedDocUuids, selectedDocNames, selectedFolderUuids, setSelectedDocUuids, setSelectedDocNames, setSelectedFolderUuids, setSelectedFolderNames,
    highlightTerms, highlightPage, highlightPageApproximate, setHighlightTerms,
    setProcessingDoc, setSelectedDocsProcessing, viewDocumentRequest, clearViewDocumentRequest,
    verificationSession, setVerificationSession, setVerificationCompletion,
    focusChat, openWorkflow, openExtraction, activateKB,
    activeProjectRootFolder, activeProjectTitle, activeProjectTeamId,
    workspaceMode, setOpenDocumentUuid,
  } = useWorkspace()
  const { toast } = useToast()
  const { currentTeam } = useTeams()
  // Folder targeted by the workflow / KB picker modals (null = closed).
  const [workflowPickerFolder, setWorkflowPickerFolder] = useState<Folder | null>(null)
  const [kbPickerFolder, setKbPickerFolder] = useState<Folder | null>(null)
  const [viewingDoc, setViewingDoc] = useState<{
    uuid: string
    title: string
    processing?: boolean
    taskStatus?: string | null
    preserveChatScope?: boolean
    previousSelection?: { uuids: string[]; names: Record<string, string> }
  } | null>(null)
  const [showRawText, setShowRawText] = useState(false)
  const [showUsage, setShowUsage] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [contentSearchState, setContentSearchState] = useState<'loading' | 'error' | null>(null)
  const [searchAttempt, setSearchAttempt] = useState(0)
  const [contentMatches, setContentMatches] = useState<ContentMatch[]>([])
  const [currentFolder, setCurrentFolder] = useState<string | null>(null)
  const listScroller = useRef<HTMLDivElement>(null)
  const listPosition = useRef(0)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const pollRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined)
  const viewingDocRef = useRef(viewingDoc)
  viewingDocRef.current = viewingDoc

  // When a project is active, root the existing file browser at its folder
  // (and reset there whenever the active project changes). This reuses the
  // whole browser — upload, subfolders, drag-to-move, rename — scoped in.
  useEffect(() => {
    setCurrentFolder(activeProjectRootFolder ?? null)
    setViewingDoc(null)
    setShowRawText(false)
    setShowUsage(false)
    setSearchQuery('')
    setSearchOpen(false)
    setContentMatches([])
    setWorkflowPickerFolder(null)
    setKbPickerFolder(null)
    listPosition.current = 0
  }, [activeProjectRootFolder, currentTeam?.uuid])

  // When a document is being viewed, ignore checkbox selection changes from FileBrowser
  // (the documents list refresh triggers onSelectionChange with empty selection, which
  // would clear selectedDocUuids and cause the chat pills to revert to generic ones)
  const handleSelectionChange = useCallback((uuids: string[]) => {
    if (!viewingDocRef.current) setSelectedDocUuids(uuids)
  }, [setSelectedDocUuids])

  const handleDocNamesChange = useCallback((names: Record<string, string>) => {
    if (!viewingDocRef.current) setSelectedDocNames(previous => ({ ...previous, ...names }))
  }, [setSelectedDocNames])

  const handleFolderSelectionChange = useCallback((uuids: string[]) => {
    if (!viewingDocRef.current) setSelectedFolderUuids(uuids)
  }, [setSelectedFolderUuids])

  const handleFolderNamesChange = useCallback((names: Record<string, string>) => {
    if (!viewingDocRef.current) setSelectedFolderNames(previous => ({ ...previous, ...names }))
  }, [setSelectedFolderNames])

  // "Ask about folder": scope the chat to just this folder, drop any
  // doc-level selection, and pull focus into the composer so the user can
  // immediately type a question. Backend chat already resolves folder_uuids.
  const handleAskAboutFolder = useCallback((folder: { uuid: string; title?: string }) => {
    setSelectedDocUuids([])
    setSelectedDocNames({})
    setSelectedFolderUuids([folder.uuid])
    setSelectedFolderNames(folder.title ? { [folder.uuid]: folder.title } : {})
    focusChat()
  }, [setSelectedDocUuids, setSelectedDocNames, setSelectedFolderUuids, setSelectedFolderNames, focusChat])

  // Pick a workflow, then run it over every document in the folder (batch:
  // one run per document). Backend expands folder_uuids -> docs.
  const handleWorkflowPicked = useCallback(async (workflowId: string) => {
    const folder = workflowPickerFolder
    setWorkflowPickerFolder(null)
    if (!folder) return
    try {
      const { session_id } = await runWorkflow(workflowId, { folder_uuids: [folder.uuid], batch_mode: true })
      openWorkflow(workflowId, session_id)
      toast(`Started workflow on “${folder.title}”`, 'success')
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : 'Failed to run workflow', 'error')
    }
  }, [workflowPickerFolder, openWorkflow, toast])

  // Pick (or create) a KB, then add the folder's documents to it.
  const handleKBPicked = useCallback(async (kbUuid: string, kbTitle: string) => {
    const folder = kbPickerFolder
    setKbPickerFolder(null)
    if (!folder) return
    try {
      const { added } = await addDocumentsToKB(kbUuid, [], [folder.uuid])
      toast(`Added ${added} document${added === 1 ? '' : 's'} to “${kbTitle}”`, 'success')
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : 'Failed to add to knowledge base', 'error')
    }
  }, [kbPickerFolder, toast])

  const handleSelectionProcessingChange = useCallback(
    (docs: Array<{ uuid: string; title: string; status: string | null }>) => {
      // Same guard as handleSelectionChange: ignore FileBrowser-driven
      // updates when the user is in the document viewer (selection there
      // is single-doc and managed directly).
      if (!viewingDocRef.current) setSelectedDocsProcessing(docs)
    },
    [setSelectedDocsProcessing],
  )

  // Open a document when requested from another panel (e.g. validation tab).
  // A request may carry its own highlight (extraction source tracking) —
  // apply it instead of the default clear, so the terms survive the open.
  useEffect(() => {
    if (viewDocumentRequest) {
      setViewingDoc({ uuid: viewDocumentRequest.uuid, title: viewDocumentRequest.title, preserveChatScope: viewDocumentRequest.preserveChatScope })
      if (!viewDocumentRequest.preserveChatScope) {
        setSelectedDocUuids([viewDocumentRequest.uuid])
        setSelectedDocNames({ [viewDocumentRequest.uuid]: viewDocumentRequest.title })
      }
      if (viewDocumentRequest.highlight) {
        setHighlightTerms(
          viewDocumentRequest.highlight.terms,
          viewDocumentRequest.highlight.page,
          viewDocumentRequest.highlight.pageApproximate,
        )
      } else {
        setHighlightTerms([])
      }
      clearViewDocumentRequest()
    }
  }, [viewDocumentRequest, clearViewDocumentRequest, setSelectedDocUuids, setSelectedDocNames, setHighlightTerms])

  // Once a verification session is active, fetch the full state from the
  // backend so we have persisted field statuses (the chat tool result only
  // seeds the UUID + extracted values).
  const verificationActive = Boolean(
    verificationSession && viewingDoc && verificationSession.document_uuid === viewingDoc.uuid,
  )
  useEffect(() => {
    if (!verificationSession) return
    if (verificationSession.status !== 'pending') return
    // Only refetch if we haven't already loaded persisted state (created_at is
    // set after a round-trip from the backend).
    if (verificationSession.created_at) return
    let cancelled = false
    getVerificationSession(verificationSession.uuid)
      .then((s) => {
        if (!cancelled) setVerificationSession(s)
      })
      .catch(() => {
        // If we can't fetch, leave the seeded session in place.
      })
    return () => {
      cancelled = true
    }
  }, [verificationSession?.uuid, verificationSession?.created_at, verificationSession?.status, setVerificationSession])

  // Publish the document the viewer is showing, so panels that link into it
  // (chat source citations) can tell "open this" from "already open". Only
  // while this panel is on screen: WorkspaceLayout collapses it to zero width
  // outside files mode, and a document nobody can see is not open.
  useEffect(() => {
    const visible = workspaceMode === 'files'
    setOpenDocumentUuid(visible ? (viewingDoc?.uuid ?? null) : null)
  }, [workspaceMode, viewingDoc?.uuid, setOpenDocumentUuid])

  useEffect(() => () => setOpenDocumentUuid(null), [setOpenDocumentUuid])

  // Sync processing state to workspace context so ChatPanel can show it
  useEffect(() => {
    if (viewingDoc?.processing) {
      setProcessingDoc({ title: viewingDoc.title, status: viewingDoc.taskStatus ?? null })
    } else {
      setProcessingDoc(null)
    }
  }, [viewingDoc?.processing, viewingDoc?.taskStatus, viewingDoc?.title, setProcessingDoc])

  // Poll processing status for the currently viewed document
  const checkStatus = useCallback(async () => {
    if (!viewingDoc?.processing) return
    try {
      const status = await pollStatus(viewingDoc.uuid)
      if (status.complete) {
        setViewingDoc(prev => prev ? { ...prev, processing: false, taskStatus: 'complete' } : prev)
      } else if (status.status !== viewingDoc.taskStatus) {
        setViewingDoc(prev => prev ? { ...prev, taskStatus: status.status } : prev)
      }
    } catch {
      // ignore poll errors
    }
  }, [viewingDoc?.uuid, viewingDoc?.processing, viewingDoc?.taskStatus])

  useEffect(() => {
    if (!viewingDoc?.processing) {
      if (pollRef.current) clearInterval(pollRef.current)
      return
    }
    // Poll immediately, then every 3 seconds
    checkStatus()
    pollRef.current = setInterval(checkStatus, 3000)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [viewingDoc?.processing, checkStatus])

  // Focus search input when opened
  useEffect(() => {
    if (searchOpen) searchInputRef.current?.focus()
  }, [searchOpen])

  // Keep list controls mounted and restore the visible list position on return.
  useLayoutEffect(() => {
    if (!viewingDoc) listScroller.current?.scrollTo({ top: listPosition.current, behavior: 'instant' })
  }, [viewingDoc])

  // Debounced content search
  useEffect(() => {
    let cancelled = false
    setContentSearchState(searchQuery.trim() ? 'loading' : null)
    setContentMatches([])
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!searchQuery.trim()) {
      setContentMatches([])
      return
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const data = await searchDocuments(searchQuery.trim())
        if (cancelled) return
        setContentSearchState(null)
        setContentMatches(
          data.items.map(item => ({
            uuid: item.uuid,
            title: item.title,
            snippet: item.snippet,
            extension: item.extension,
            num_pages: item.num_pages,
            created_at: item.created_at || '',
            updated_at: item.updated_at || '',
            processing: item.processing,
            valid: item.valid,
            task_status: item.task_status,
            folder: item.folder,
            token_count: item.token_count,
          }))
        )
      } catch {
        if (cancelled) return
        setContentSearchState('error')
        setContentMatches([])
      }
    }, 300)
    return () => {
      cancelled = true
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [searchQuery, searchAttempt])

  const handleCloseSearch = () => {
    setSearchOpen(false)
    setSearchQuery('')
    setContentMatches([])
  }

  return (
    <aside aria-label="Documents" className="flex h-full min-h-0 flex-col overflow-hidden bg-panel-bg relative">
      {viewingDoc && <header className="workspace-document-header">
        <button type="button" aria-label="Close document" className="workspace-header-icon"
          onClick={() => { setViewingDoc(null); if (!viewingDoc.preserveChatScope) { setSelectedDocUuids(viewingDoc.previousSelection?.uuids ?? []); setSelectedDocNames(viewingDoc.previousSelection?.names ?? {}) } setHighlightTerms([]) }}>
          <ArrowLeft size={20} />
        </button>
        <h2>{viewingDoc.title}</h2>
        <div className="workspace-section-actions">
          <button type="button" onClick={() => setShowUsage(true)} className="workspace-header-icon" title="Where is this used?" aria-label="Where is this used?"><Link2 size={20} /></button>
          <button type="button" onClick={() => setShowRawText(true)} className="workspace-header-icon" title="View extracted text" aria-label="View extracted text"><FileText size={20} /></button>
        </div>
      </header>}

      {/* Content area */}
      {viewingDoc && (
        <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
          <DocumentViewer
            docUuid={viewingDoc.uuid}
            highlightTerms={highlightTerms}
            highlightPage={highlightPage}
            highlightPageApproximate={highlightPageApproximate}
            onClearHighlights={verificationActive ? undefined : () => setHighlightTerms([])}
            processing={viewingDoc.processing}
            taskStatus={viewingDoc.taskStatus}
            hideHighlightNavBar={verificationActive}
          />
          {verificationActive && verificationSession && (
            <div
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                bottom: 12,
                pointerEvents: 'none',
                zIndex: 200,
              }}
            >
              <div style={{ pointerEvents: 'auto' }}>
                <VerificationNavBar
                  session={verificationSession}
                  onSessionUpdated={setVerificationSession}
                  onActiveValueChange={(value) => {
                    // Drive the PDF's runtime string search to the active field value.
                    setHighlightTerms(value ? [value] : [])
                  }}
                  onCompleted={({ session, testCaseUuid, outcome }) => {
                    const approved = session.fields.filter((f) => f.status === 'approved').length
                    const corrected = session.fields.filter((f) => f.status === 'corrected').length
                    const skipped = session.fields.filter((f) => f.status === 'skipped').length
                    setVerificationCompletion({
                      sessionId: session.uuid,
                      extractionSetUuid: session.search_set_uuid,
                      documentTitle: session.document_title,
                      testCaseUuid,
                      outcome,
                      approvedCount: approved,
                      correctedCount: corrected,
                      skippedCount: skipped,
                    })
                    setVerificationSession(null)
                    setHighlightTerms([])
                  }}
                />
              </div>
            </div>
          )}
        </div>
      )}
        <div ref={listScroller} onScroll={event => { if (!viewingDoc) listPosition.current = event.currentTarget.scrollTop }} className="overflow-auto hide-scrollbar" style={{ display: viewingDoc ? 'none' : undefined, flex: 1, minHeight: 0, paddingBottom: 60 }}>
          <FileBrowser
            searchAction={!searchOpen && <button type="button" title="Search files" aria-label="Search files" onClick={() => setSearchOpen(true)} className="workspace-header-icon"><Search size={18} /></button>}
            searchField={searchOpen && <div className="workspace-file-search">
              <Search size={16} aria-hidden="true" />
              <input ref={searchInputRef} type="search" aria-label="Search files and content" placeholder="Search files and content..." value={searchQuery} onChange={event => setSearchQuery(event.target.value)} />
              <button type="button" aria-label="Close search" className="workspace-header-icon" onClick={handleCloseSearch}><X size={18} /></button>
            </div>}
            selectedDocumentUuids={selectedDocUuids}
            selectedFolderUuids={selectedFolderUuids}
            searchQuery={searchQuery}
            contentMatches={contentMatches}
            contentSearchState={contentSearchState}
            onRetryContentSearch={() => setSearchAttempt(value => value + 1)}
            currentFolder={currentFolder}
            onFolderNavigate={setCurrentFolder}
            rootFolder={activeProjectRootFolder}
            rootLabel={activeProjectTitle}
            teamScopeUuid={activeProjectTeamId ?? undefined}
            onDocClick={(doc) => {
              const next = {
                uuid: doc.uuid,
                title: doc.title,
                processing: doc.processing,
                taskStatus: doc.task_status,
                previousSelection: { uuids: selectedDocUuids, names: selectedDocNames },
              }
              // Sync-update the ref so handleSelectionChange's guard sees
              // "viewing" immediately. When the auto-open-after-upload effect
              // and the checkbox-sync effect fire in the same commit, the
              // sync effect would otherwise clear the selection we just set.
              viewingDocRef.current = next
              setViewingDoc(next)
              setSelectedDocUuids([doc.uuid])
              setSelectedDocNames({ [doc.uuid]: doc.title })
              setHighlightTerms([])
            }}
            onSelectionChange={handleSelectionChange}
            onDocNamesChange={handleDocNamesChange}
            onFolderSelectionChange={handleFolderSelectionChange}
            onFolderNamesChange={handleFolderNamesChange}
            onSelectionProcessingChange={handleSelectionProcessingChange}
            onAskAboutFolder={handleAskAboutFolder}
            onRunWorkflowOnFolder={setWorkflowPickerFolder}
            onAddFolderToKB={setKbPickerFolder}
          />
        </div>

      {showUsage && viewingDoc && (
        <DocumentUsageDialog
          docUuid={viewingDoc.uuid}
          docTitle={viewingDoc.title}
          onClose={() => setShowUsage(false)}
          onOpenWorkflow={(id) => openWorkflow(id)}
          onOpenExtraction={(uuid) => openExtraction(uuid)}
          onOpenKnowledgeBase={(uuid, title) => activateKB(uuid, title)}
        />
      )}
      {showRawText && viewingDoc && (
        <RawTextModal docUuid={viewingDoc.uuid} onClose={() => setShowRawText(false)} />
      )}

      {workflowPickerFolder && (
        <ItemPickerModal
          kind="workflow"
          onSelect={(id) => handleWorkflowPicked(id)}
          onClose={() => setWorkflowPickerFolder(null)}
        />
      )}

      {kbPickerFolder && (
        <KBPickerModal
          folderTitle={kbPickerFolder.title}
          onSelect={handleKBPicked}
          onClose={() => setKbPickerFolder(null)}
        />
      )}
    </aside>
  )
}
