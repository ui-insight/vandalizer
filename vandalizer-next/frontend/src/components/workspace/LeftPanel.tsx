import { useState } from 'react'
import { ArrowLeft, FileText } from 'lucide-react'
import { FileBrowser } from '../files/FileBrowser'
import { DocumentViewer } from '../files/DocumentViewer'
import { RawTextModal } from '../files/RawTextModal'
import { useWorkspace } from '../../contexts/WorkspaceContext'

export function LeftPanel() {
  const { setSelectedDocUuids } = useWorkspace()
  const [viewingDoc, setViewingDoc] = useState<{ uuid: string; title: string } | null>(null)
  const [showRawText, setShowRawText] = useState(false)

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
        <div style={{ paddingRight: 15, width: 50 }}>
          {viewingDoc && (
            <button
              onClick={() => setShowRawText(true)}
              className="bg-transparent border-0 p-0 cursor-pointer"
            >
              <FileText className="h-5 w-5 text-white" />
            </button>
          )}
        </div>
      </div>

      {/* Content area */}
      {viewingDoc ? (
        <div style={{ height: 'calc(100% - 50px)' }}>
          <DocumentViewer docUuid={viewingDoc.uuid} />
        </div>
      ) : (
        <div className="overflow-auto hide-scrollbar" style={{ height: 'calc(100% - 50px)', paddingTop: 10, paddingBottom: 60 }}>
          <FileBrowser
            onDocClick={(doc) => {
              setViewingDoc({ uuid: doc.uuid, title: doc.title })
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
