import { useState, useEffect, useRef, useCallback } from 'react'
import { ArrowLeft, FileText, Search, X } from 'lucide-react'
import { FileBrowser } from '../files/FileBrowser'
import type { ContentMatch } from '../files/FileBrowser'
import { DocumentViewer } from '../files/DocumentViewer'
import { RawTextModal } from '../files/RawTextModal'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { pollStatus, searchDocuments } from '../../api/documents'

export function LeftPanel() {
  const { setSelectedDocUuids, setSelectedFolderUuids, highlightTerms, setProcessingDoc, viewDocumentRequest, clearViewDocumentRequest } = useWorkspace()
  const [viewingDoc, setViewingDoc] = useState<{
    uuid: string
    title: string
    processing?: boolean
    taskStatus?: string | null
  } | null>(null)
  const [showRawText, setShowRawText] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [contentMatches, setContentMatches] = useState<ContentMatch[]>([])
  const [currentFolder, setCurrentFolder] = useState<string | null>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const pollRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined)
  const viewingDocRef = useRef(viewingDoc)
  viewingDocRef.current = viewingDoc

  // When a document is being viewed, ignore checkbox selection changes from FileBrowser
  // (the documents list refresh triggers onSelectionChange with empty selection, which
  // would clear selectedDocUuids and cause the chat pills to revert to generic ones)
  const handleSelectionChange = useCallback((uuids: string[]) => {
    if (!viewingDocRef.current) setSelectedDocUuids(uuids)
  }, [setSelectedDocUuids])

  const handleFolderSelectionChange = useCallback((uuids: string[]) => {
    if (!viewingDocRef.current) setSelectedFolderUuids(uuids)
  }, [setSelectedFolderUuids])

  // Open a document when requested from another panel (e.g. validation tab)
  useEffect(() => {
    if (viewDocumentRequest) {
      setViewingDoc({ uuid: viewDocumentRequest.uuid, title: viewDocumentRequest.title })
      setSelectedDocUuids([viewDocumentRequest.uuid])
      clearViewDocumentRequest()
    }
  }, [viewDocumentRequest, clearViewDocumentRequest, setSelectedDocUuids])

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

  // Close search when navigating to a doc
  useEffect(() => {
    if (viewingDoc) {
      setSearchOpen(false)
      setSearchQuery('')
      setContentMatches([])
    }
  }, [viewingDoc])

  // Debounced content search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!searchQuery.trim()) {
      setContentMatches([])
      return
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const data = await searchDocuments(searchQuery.trim())
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
        setContentMatches([])
      }
    }, 300)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [searchQuery])

  const handleCloseSearch = () => {
    setSearchOpen(false)
    setSearchQuery('')
    setContentMatches([])
  }

  return (
    <div className="h-full overflow-hidden bg-panel-bg relative">
      {/* Black header bar - matches Flask .main-panel .header */}
      <div
        className="relative z-[300] flex items-center"
        style={{
          height: 50,
          backgroundColor: '#191919',
          boxShadow: '0 0px 23px -8px rgb(211, 211, 211)',
          padding: '0 15px',
        }}
      >
        {/* Back button */}
        <div style={{ paddingLeft: 15, width: 50 }}>
          {viewingDoc && (
            <button
              onClick={() => { setViewingDoc(null); setSelectedDocUuids([]) }}
              className="bg-transparent border-0 p-0 cursor-pointer"
            >
              <ArrowLeft className="h-6 w-6 text-white" />
            </button>
          )}
        </div>

        {/* Title or search input - centered */}
        <div className="flex-1 text-center">
          {searchOpen && !viewingDoc ? (
            <div className="flex items-center gap-2 mx-auto" style={{ maxWidth: 'calc(100% - 60px)' }}>
              <Search className="h-4 w-4 text-gray-400 shrink-0" />
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search files and content..."
                style={{
                  flex: 1, border: 'none', background: 'none', outline: 'none',
                  fontSize: 15, color: '#fff',
                }}
              />
              <button
                onClick={handleCloseSearch}
                className="bg-transparent border-0 p-0 cursor-pointer"
              >
                <X className="h-4 w-4 text-gray-400 hover:text-white" />
              </button>
            </div>
          ) : (
            <p
              className="m-0 truncate text-white"
              style={{
                fontSize: 18,
                fontWeight: 600,
                maxWidth: 'calc(100% - 60px)',
                margin: '0 auto',
              }}
            >
              {viewingDoc ? viewingDoc.title : 'Select or Upload PDFs'}
            </p>
          )}
        </div>

        {/* Right controls */}
        <div style={{ paddingRight: 15, width: 50, display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-end' }}>
          {viewingDoc ? (
            <button
              onClick={() => setShowRawText(true)}
              className="bg-transparent border-0 p-0 cursor-pointer"
            >
              <FileText className="h-5 w-5 text-white" />
            </button>
          ) : !searchOpen ? (
            <button
              onClick={() => setSearchOpen(true)}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 32, height: 32, borderRadius: 6, border: 'none',
                background: 'none', cursor: 'pointer', color: '#fff',
              }}
              title="Search files"
            >
              <Search size={16} />
            </button>
          ) : null}
        </div>
      </div>

      {/* Content area */}
      {viewingDoc ? (
        <div style={{ height: 'calc(100% - 50px)' }}>
          <DocumentViewer
            docUuid={viewingDoc.uuid}
            highlightTerms={highlightTerms}
            processing={viewingDoc.processing}
            taskStatus={viewingDoc.taskStatus}
          />
        </div>
      ) : (
        <div className="overflow-auto hide-scrollbar" style={{ height: 'calc(100% - 50px)', paddingTop: 10, paddingBottom: 60 }}>
          <FileBrowser
            searchQuery={searchQuery}
            contentMatches={contentMatches}
            currentFolder={currentFolder}
            onFolderNavigate={setCurrentFolder}
            onDocClick={(doc) => {
              setViewingDoc({
                uuid: doc.uuid,
                title: doc.title,
                processing: doc.processing,
                taskStatus: doc.task_status,
              })
              setSelectedDocUuids([doc.uuid])
            }}
            onSelectionChange={handleSelectionChange}
            onFolderSelectionChange={handleFolderSelectionChange}
          />
        </div>
      )}

      {showRawText && viewingDoc && (
        <RawTextModal docUuid={viewingDoc.uuid} onClose={() => setShowRawText(false)} />
      )}
    </div>
  )
}
