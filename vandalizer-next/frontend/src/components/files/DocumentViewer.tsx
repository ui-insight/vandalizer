import { useCallback, useRef, useState } from 'react'
import { ZoomIn, ZoomOut, RotateCw, Maximize2, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { downloadFileUrl } from '../../api/files'

interface DocumentViewerProps {
  docUuid: string
}

const ZOOM_LEVELS = [0.5, 0.75, 1, 1.25, 1.5, 2]

export function DocumentViewer({ docUuid }: DocumentViewerProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [zoom, setZoom] = useState(2) // index into ZOOM_LEVELS, default 1 (100%)
  const [showToolbar, setShowToolbar] = useState(true)

  const zoomIn = useCallback(() => {
    setZoom(prev => Math.min(prev + 1, ZOOM_LEVELS.length - 1))
  }, [])

  const zoomOut = useCallback(() => {
    setZoom(prev => Math.max(prev - 1, 0))
  }, [])

  const resetZoom = useCallback(() => {
    setZoom(2) // 100%
  }, [])

  const zoomLevel = ZOOM_LEVELS[zoom]

  const btnStyle: React.CSSProperties = {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: 32, height: 32, borderRadius: 6, border: '1px solid #d1d5db',
    background: '#fff', cursor: 'pointer', color: '#374151',
    fontSize: 13, fontWeight: 500,
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative' }}>
      {/* Toolbar */}
      {showToolbar && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
          padding: '6px 12px', borderBottom: '1px solid #e5e7eb', backgroundColor: '#f9fafb',
          flexShrink: 0,
        }}>
          <button onClick={zoomOut} style={btnStyle} title="Zoom out" disabled={zoom <= 0}>
            <ZoomOut size={16} />
          </button>
          <button onClick={resetZoom} style={{ ...btnStyle, width: 'auto', padding: '0 10px' }} title="Reset zoom">
            {Math.round(zoomLevel * 100)}%
          </button>
          <button onClick={zoomIn} style={btnStyle} title="Zoom in" disabled={zoom >= ZOOM_LEVELS.length - 1}>
            <ZoomIn size={16} />
          </button>
          <div style={{ width: 1, height: 20, backgroundColor: '#d1d5db', margin: '0 4px' }} />
          <button
            onClick={() => {
              // Open in new tab for full screen
              window.open(downloadFileUrl(docUuid), '_blank')
            }}
            style={btnStyle}
            title="Open in new tab"
          >
            <Maximize2 size={16} />
          </button>
        </div>
      )}

      {/* Document */}
      <div style={{
        flex: 1, overflow: 'auto', display: 'flex', justifyContent: 'center',
        backgroundColor: '#525659',
      }}>
        <div style={{
          transform: `scale(${zoomLevel})`,
          transformOrigin: 'top center',
          width: `${100 / zoomLevel}%`,
          height: `${100 / zoomLevel}%`,
          minHeight: '100%',
        }}>
          <iframe
            ref={iframeRef}
            src={downloadFileUrl(docUuid)}
            style={{ width: '100%', height: '100%', border: 'none' }}
            title="Document viewer"
          />
        </div>
      </div>
    </div>
  )
}
