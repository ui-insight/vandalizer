import { useState, useEffect, useRef, useCallback } from 'react'
import { ArrowLeft, FileText } from 'lucide-react'
import { FileBrowser } from '../files/FileBrowser'
import { DocumentViewer } from '../files/DocumentViewer'
import { RawTextModal } from '../files/RawTextModal'
import { GlobalSearch } from '../files/GlobalSearch'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { pollStatus } from '../../api/documents'

export function LeftPanel() {
  const { setSelectedDocUuids, highlightTerms, setProcessingDoc } = useWorkspace()
  const [viewingDoc, setViewingDoc] = useState<{
    uuid: string
    title: string
    processing?: boolean
    taskStatus?: string | null
  } | null>(null)
  const [showRawText, setShowRawText] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined)

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
              onClick={() => setViewingDoc(null)}
              className="bg-transparent border-0 p-0 cursor-pointer"
            >
              <ArrowLeft className="h-6 w-6 text-white" />
            </button>
          )}
        </div>

        {/* Title - centered */}
        <div className="flex-1 text-center">
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
          ) : (
            <GlobalSearch
              onDocClick={(doc) => {
                setViewingDoc({ uuid: doc.uuid, title: doc.title })
                setSelectedDocUuids([doc.uuid])
              }}
            />
          )}
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
            onDocClick={(doc) => {
              setViewingDoc({
                uuid: doc.uuid,
                title: doc.title,
                processing: doc.processing,
                taskStatus: doc.task_status,
              })
              setSelectedDocUuids([doc.uuid])
            }}
          />
        </div>
      )}

      {showRawText && viewingDoc && (
        <RawTextModal docUuid={viewingDoc.uuid} onClose={() => setShowRawText(false)} />
      )}
    </div>
  )
}
