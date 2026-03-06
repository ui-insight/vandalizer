import { useEffect, useState } from 'react'
import { ZoomIn, ZoomOut, Maximize2 } from 'lucide-react'
import { downloadFileUrl } from '../../api/files'
import * as XLSX from 'xlsx'

interface SpreadsheetViewerProps {
  docUuid: string
  processing?: boolean
  taskStatus?: string | null
}

const ZOOM_LEVELS = [0.5, 0.75, 1, 1.25, 1.5, 2]

export function SpreadsheetViewer({ docUuid, processing, taskStatus }: SpreadsheetViewerProps) {
  const [zoom, setZoom] = useState(2)
  const [headers, setHeaders] = useState<string[]>([])
  const [rows, setRows] = useState<string[][]>([])
  const [sheets, setSheets] = useState<string[]>([])
  const [activeSheet, setActiveSheet] = useState(0)
  const [workbook, setWorkbook] = useState<XLSX.WorkBook | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const url = downloadFileUrl(docUuid)
  const zoomLevel = ZOOM_LEVELS[zoom]

  // Fetch and parse spreadsheet
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    fetch(url, { credentials: 'include' })
      .then(async (resp) => {
        if (cancelled) return
        const ct = resp.headers.get('content-type') || ''

        if (ct.includes('csv') || ct.includes('text/plain')) {
          const text = await resp.text()
          if (cancelled) return
          const wb = XLSX.read(text, { type: 'string' })
          setWorkbook(wb)
          setSheets(wb.SheetNames)
          loadSheet(wb, 0)
        } else {
          const buf = await resp.arrayBuffer()
          if (cancelled) return
          const wb = XLSX.read(buf, { type: 'array' })
          setWorkbook(wb)
          setSheets(wb.SheetNames)
          loadSheet(wb, 0)
        }
        setLoading(false)
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load spreadsheet')
          setLoading(false)
        }
      })

    return () => { cancelled = true }
  }, [url])

  function loadSheet(wb: XLSX.WorkBook, index: number) {
    const sheet = wb.Sheets[wb.SheetNames[index]]
    const data: string[][] = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: '' })
    if (data.length > 0) {
      setHeaders(data[0].map(String))
      setRows(data.slice(1).map(row => row.map(String)))
    } else {
      setHeaders([])
      setRows([])
    }
    setActiveSheet(index)
  }

  const handleSheetChange = (index: number) => {
    if (workbook) loadSheet(workbook, index)
  }

  const btnStyle: React.CSSProperties = {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: 32, height: 32, borderRadius: 6, border: '1px solid #d1d5db',
    background: '#fff', cursor: 'pointer', color: '#374151',
    fontSize: 13, fontWeight: 500,
  }

  if (loading) {
    return (
      <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f9fafb' }}>
        <div style={{ color: '#9ca3af', fontSize: 14 }}>Loading spreadsheet...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f9fafb' }}>
        <div style={{ color: '#ef4444', fontSize: 14 }}>{error}</div>
      </div>
    )
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative' }}>
      {/* Processing overlay */}
      {processing && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, zIndex: 50,
          display: 'flex', justifyContent: 'center', padding: '20px 24px',
        }}>
          <div style={{
            width: '100%', maxWidth: 420, padding: '20px 24px', borderRadius: 'var(--ui-radius, 12px)',
            background: 'linear-gradient(135deg, var(--highlight-complement, #6a11cb), color-mix(in srgb, var(--highlight-color, #f1b300) 70%, #ffffff 30%))',
            color: '#fff', boxShadow: '0 4px 20px rgba(0,0,0,0.2)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white shrink-0" />
              <div>
                <div style={{ fontSize: 14, fontWeight: 600 }}>Processing Your Document...</div>
                <div style={{ fontSize: 12, opacity: 0.8, marginTop: 3 }}>Please wait while we prepare your document.</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
        padding: '6px 12px', borderBottom: '1px solid #e5e7eb', backgroundColor: '#f9fafb',
        flexShrink: 0,
      }}>
        <button onClick={() => setZoom(prev => Math.max(prev - 1, 0))} style={btnStyle} title="Zoom out" disabled={zoom <= 0}>
          <ZoomOut size={16} />
        </button>
        <button onClick={() => setZoom(2)} style={{ ...btnStyle, width: 'auto', padding: '0 10px' }} title="Reset zoom">
          {Math.round(zoomLevel * 100)}%
        </button>
        <button onClick={() => setZoom(prev => Math.min(prev + 1, ZOOM_LEVELS.length - 1))} style={btnStyle} title="Zoom in" disabled={zoom >= ZOOM_LEVELS.length - 1}>
          <ZoomIn size={16} />
        </button>
        <div style={{ width: 1, height: 20, backgroundColor: '#d1d5db', margin: '0 4px' }} />
        <button onClick={() => window.open(url, '_blank')} style={btnStyle} title="Open in new tab">
          <Maximize2 size={16} />
        </button>
      </div>

      {/* Sheet tabs */}
      {sheets.length > 1 && (
        <div style={{
          display: 'flex', gap: 0, borderBottom: '1px solid #e5e7eb',
          backgroundColor: '#f3f4f6', flexShrink: 0, overflowX: 'auto',
        }}>
          {sheets.map((name, i) => (
            <button
              key={name}
              onClick={() => handleSheetChange(i)}
              style={{
                padding: '6px 16px', fontSize: 12, fontWeight: i === activeSheet ? 600 : 400,
                color: i === activeSheet ? '#111827' : '#6b7280',
                backgroundColor: i === activeSheet ? '#fff' : 'transparent',
                borderBottom: i === activeSheet ? '2px solid var(--highlight-color, #eab308)' : '2px solid transparent',
                border: 'none', borderRight: '1px solid #e5e7eb',
                cursor: 'pointer', whiteSpace: 'nowrap', fontFamily: 'inherit',
              }}
            >
              {name}
            </button>
          ))}
        </div>
      )}

      {/* Table */}
      <div style={{ flex: 1, overflow: 'auto', backgroundColor: '#fff' }}>
        <div style={{
          transform: `scale(${zoomLevel})`,
          transformOrigin: 'top left',
          width: `${100 / zoomLevel}%`,
        }}>
          {headers.length === 0 && rows.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af', fontSize: 14 }}>
              This sheet is empty
            </div>
          ) : (
            <table style={{
              width: '100%', borderCollapse: 'collapse', fontSize: 13,
            }}>
              {headers.length > 0 && (
                <thead>
                  <tr>
                    <th style={{
                      padding: '8px 12px', textAlign: 'center', fontSize: 11, fontWeight: 600,
                      color: '#9ca3af', backgroundColor: '#f9fafb',
                      borderBottom: '2px solid #e5e7eb', borderRight: '1px solid #e5e7eb',
                      position: 'sticky', top: 0, zIndex: 2, width: 44,
                    }}>
                      #
                    </th>
                    {headers.map((h, i) => (
                      <th key={i} style={{
                        padding: '8px 12px', textAlign: 'left', fontWeight: 600,
                        color: '#374151', backgroundColor: '#f9fafb',
                        borderBottom: '2px solid #e5e7eb', borderRight: '1px solid #f3f4f6',
                        position: 'sticky', top: 0, zIndex: 2,
                        whiteSpace: 'nowrap',
                      }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
              )}
              <tbody>
                {rows.map((row, ri) => (
                  <tr key={ri} style={{ backgroundColor: ri % 2 === 0 ? '#fff' : '#fafafa' }}>
                    <td style={{
                      padding: '6px 12px', textAlign: 'center', fontSize: 11,
                      color: '#9ca3af', borderBottom: '1px solid #f3f4f6',
                      borderRight: '1px solid #e5e7eb', backgroundColor: '#f9fafb',
                    }}>
                      {ri + 1}
                    </td>
                    {headers.map((_, ci) => (
                      <td key={ci} style={{
                        padding: '6px 12px', color: '#374151',
                        borderBottom: '1px solid #f3f4f6',
                        borderRight: '1px solid #f3f4f6',
                        whiteSpace: 'nowrap', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis',
                      }}>
                        {row[ci] ?? ''}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
