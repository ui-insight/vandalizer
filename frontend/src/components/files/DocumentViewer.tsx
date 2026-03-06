import { useCallback, useEffect, useRef, useState } from 'react'
import { ZoomIn, ZoomOut, Maximize2, ChevronLeft, ChevronRight } from 'lucide-react'
import { downloadFileUrl } from '../../api/files'
import { SpreadsheetViewer } from './SpreadsheetViewer'
import * as pdfjsLib from 'pdfjs-dist'

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.mjs',
  import.meta.url,
).toString()

interface DocumentViewerProps {
  docUuid: string
  highlightTerms?: string[]
  processing?: boolean
  taskStatus?: string | null
}

const ZOOM_LEVELS = [0.5, 0.75, 1, 1.25, 1.5, 2]
const HIGHLIGHT_COLOR = '#eab308'

const STATUS_MESSAGES: Record<string, { title: string; message: string }> = {
  layout: {
    title: 'Converting & Preparing Your Document...',
    message: "We're converting your document so it can be read and analyzed accurately.",
  },
  ocr: {
    title: 'Extracting Text From Your Document...',
    message: 'Running OCR to extract text content from your document.',
  },
  security: {
    title: 'Scanning Your Document for Security...',
    message: "Please hang tight — we're checking for any sensitive information.",
  },
  readying: {
    title: 'Preparing Your Document...',
    message: 'Almost done — indexing your document for search and analysis.',
  },
}

export function DocumentViewer({ docUuid, highlightTerms = [], processing, taskStatus }: DocumentViewerProps) {
  const [zoom, setZoom] = useState(2) // index into ZOOM_LEVELS, default 100%
  const [isPdf, setIsPdf] = useState<boolean | null>(null) // null = loading
  const [isSpreadsheet, setIsSpreadsheet] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const pdfDocRef = useRef<pdfjsLib.PDFDocumentProxy | null>(null)
  const pdfDataRef = useRef<ArrayBuffer | null>(null)
  const renderingRef = useRef(false)
  const [totalHighlights, setTotalHighlights] = useState(0)
  const [currentHighlight, setCurrentHighlight] = useState(0)

  const zoomLevel = ZOOM_LEVELS[zoom]
  const url = downloadFileUrl(docUuid)

  // Fetch PDF data with credentials and detect content type
  useEffect(() => {
    let cancelled = false
    setIsPdf(null)
    setIsSpreadsheet(false)
    pdfDataRef.current = null

    fetch(url, { credentials: 'include', method: 'HEAD' })
      .then(async (resp) => {
        if (cancelled) return
        const ct = resp.headers.get('content-type') || ''
        if (ct.includes('csv') || ct.includes('spreadsheet') || ct.includes('excel') || ct.includes('ms-excel')) {
          setIsSpreadsheet(true)
          setIsPdf(false)
        } else if (ct.includes('pdf')) {
          const fullResp = await fetch(url, { credentials: 'include' })
          const data = await fullResp.arrayBuffer()
          if (cancelled) return
          pdfDataRef.current = data
          setIsPdf(true)
        } else {
          setIsPdf(false)
        }
      })
      .catch(() => {
        if (!cancelled) setIsPdf(false)
      })

    return () => { cancelled = true }
  }, [url])

  // Load PDF document from fetched data
  useEffect(() => {
    if (isPdf !== true || !pdfDataRef.current) return
    let cancelled = false

    const loadTask = pdfjsLib.getDocument({ data: pdfDataRef.current.slice(0) })
    loadTask.promise
      .then((doc) => {
        if (cancelled) {
          doc.destroy()
          return
        }
        pdfDocRef.current = doc
        renderAllPages(doc)
      })
      .catch(() => {
        if (!cancelled) setIsPdf(false)
      })

    return () => {
      cancelled = true
      loadTask.destroy?.()
      if (pdfDocRef.current) {
        pdfDocRef.current.destroy()
        pdfDocRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPdf])

  // Re-render pages when zoom changes
  useEffect(() => {
    if (isPdf !== true || !pdfDocRef.current) return
    renderAllPages(pdfDocRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoomLevel])

  // Re-apply highlights when terms change
  useEffect(() => {
    if (isPdf !== true || !pdfDocRef.current) return
    applyHighlights(pdfDocRef.current, highlightTerms)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlightTerms])

  const renderAllPages = useCallback(async (doc: pdfjsLib.PDFDocumentProxy) => {
    if (renderingRef.current) return
    renderingRef.current = true

    const container = containerRef.current
    if (!container) { renderingRef.current = false; return }

    // Clear existing pages
    container.innerHTML = ''
    const dpr = window.devicePixelRatio || 1

    for (let i = 1; i <= doc.numPages; i++) {
      const page = await doc.getPage(i)
      const viewport = page.getViewport({ scale: zoomLevel })

      // Page wrapper
      const wrapper = document.createElement('div')
      wrapper.style.position = 'relative'
      wrapper.style.width = `${Math.floor(viewport.width)}px`
      wrapper.style.margin = '10px auto'
      wrapper.style.boxShadow = '0 2px 8px rgba(0,0,0,0.15)'
      wrapper.style.backgroundColor = '#fff'
      wrapper.dataset.pageNum = String(i)

      // Canvas
      const canvas = document.createElement('canvas')
      canvas.width = Math.floor(viewport.width * dpr)
      canvas.height = Math.floor(viewport.height * dpr)
      canvas.style.width = `${Math.floor(viewport.width)}px`
      canvas.style.height = `${Math.floor(viewport.height)}px`
      canvas.style.display = 'block'

      // Overlay for highlights
      const overlay = document.createElement('div')
      overlay.className = 'pdf-overlay'
      overlay.style.position = 'absolute'
      overlay.style.left = '0'
      overlay.style.top = '0'
      overlay.style.width = canvas.style.width
      overlay.style.height = canvas.style.height
      overlay.style.pointerEvents = 'none'

      wrapper.appendChild(canvas)
      wrapper.appendChild(overlay)
      container.appendChild(wrapper)

      // Render page on canvas
      const ctx = canvas.getContext('2d')!
      await page.render({
        canvasContext: ctx,
        viewport,
        transform: [dpr, 0, 0, dpr, 0, 0],
      }).promise
    }

    renderingRef.current = false

    // Apply highlights after rendering
    if (highlightTerms.length > 0) {
      applyHighlights(doc, highlightTerms)
    }
  }, [zoomLevel, highlightTerms])

  const applyHighlights = useCallback(async (doc: pdfjsLib.PDFDocumentProxy, terms: string[]) => {
    const container = containerRef.current
    if (!container) return

    // Clear all existing highlights
    container.querySelectorAll('.pdf-highlight').forEach(el => el.remove())

    if (terms.length === 0) {
      setTotalHighlights(0)
      setCurrentHighlight(0)
      return
    }

    let count = 0

    for (let i = 1; i <= doc.numPages; i++) {
      const page = await doc.getPage(i)
      const viewport = page.getViewport({ scale: zoomLevel })
      const textContent = await page.getTextContent()
      const wrapper = container.querySelector(`[data-page-num="${i}"]`)
      const overlay = wrapper?.querySelector('.pdf-overlay')
      if (!overlay) continue

      for (const item of textContent.items) {
        if (!('str' in item)) continue
        const textItem = item as { str: string; transform: number[]; width: number; height: number }
        const textStr = textItem.str
        if (!textStr) continue

        const textLower = textStr.toLowerCase()
        const matched = terms.some(t => t && textLower.includes(t.toLowerCase()))
        if (!matched) continue

        const scale = viewport.scale
        const [, , , , tx, ty] = textItem.transform
        const x = tx * scale
        const y = viewport.height - (ty * scale) - (textItem.height * scale)

        const hl = document.createElement('div')
        hl.className = 'pdf-highlight'
        hl.dataset.highlightIndex = String(count)
        Object.assign(hl.style, {
          position: 'absolute',
          left: `${x}px`,
          top: `${y}px`,
          width: `${textItem.width * scale}px`,
          height: `${textItem.height * scale}px`,
          backgroundColor: HIGHLIGHT_COLOR,
          opacity: '0.45',
          pointerEvents: 'none',
          borderRadius: '2px',
        })
        overlay.appendChild(hl)
        count++
      }
    }

    setTotalHighlights(count)
    if (count > 0) {
      setCurrentHighlight(0)
      // Scroll to first highlight
      setTimeout(() => scrollToHighlightByIndex(0), 150)
    }
  }, [zoomLevel])

  const scrollToHighlightByIndex = (index: number) => {
    const container = containerRef.current
    if (!container) return

    const highlights = container.querySelectorAll('.pdf-highlight')
    if (highlights.length === 0 || index < 0 || index >= highlights.length) return

    // Update opacity on all highlights
    highlights.forEach((hl, idx) => {
      ;(hl as HTMLElement).style.opacity = idx === index ? '0.75' : '0.45'
    })

    const target = highlights[index] as HTMLElement
    const scrollParent = container.parentElement
    if (!scrollParent) return

    const targetRect = target.getBoundingClientRect()
    const parentRect = scrollParent.getBoundingClientRect()
    const scrollTop = scrollParent.scrollTop + (targetRect.top - parentRect.top) - 150

    scrollParent.scrollTo({
      top: Math.max(0, scrollTop),
      behavior: 'smooth',
    })
  }

  const goToHighlight = useCallback((direction: 'next' | 'prev') => {
    if (totalHighlights === 0) return
    setCurrentHighlight(prev => {
      let next: number
      if (direction === 'next') {
        next = prev + 1 >= totalHighlights ? 0 : prev + 1
      } else {
        next = prev - 1 < 0 ? totalHighlights - 1 : prev - 1
      }
      setTimeout(() => scrollToHighlightByIndex(next), 50)
      return next
    })
  }, [totalHighlights])

  const zoomIn = useCallback(() => {
    setZoom(prev => Math.min(prev + 1, ZOOM_LEVELS.length - 1))
  }, [])

  const zoomOut = useCallback(() => {
    setZoom(prev => Math.max(prev - 1, 0))
  }, [])

  const resetZoom = useCallback(() => {
    setZoom(2)
  }, [])

  const btnStyle: React.CSSProperties = {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: 32, height: 32, borderRadius: 6, border: '1px solid #d1d5db',
    background: '#fff', cursor: 'pointer', color: '#374151',
    fontSize: 13, fontWeight: 500,
  }

  // Processing overlay - shown when document is still being processed
  const processingOverlay = processing ? (
    <div style={{
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      zIndex: 50,
      display: 'flex',
      justifyContent: 'center',
      padding: '20px 24px',
    }}>
      <div style={{
        width: '100%',
        maxWidth: 420,
        padding: '20px 24px',
        borderRadius: 'var(--ui-radius, 12px)',
        background: 'linear-gradient(135deg, var(--highlight-complement, #6a11cb), color-mix(in srgb, var(--highlight-color, #f1b300) 70%, #ffffff 30%))',
        color: '#fff',
        boxShadow: '0 4px 20px rgba(0,0,0,0.2)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white shrink-0" />
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.3 }}>
              {STATUS_MESSAGES[taskStatus || '']?.title || 'Processing Your Document...'}
            </div>
            <div style={{ fontSize: 12, opacity: 0.8, marginTop: 3 }}>
              {STATUS_MESSAGES[taskStatus || '']?.message || 'Please wait while we prepare your document.'}
            </div>
          </div>
        </div>
        {/* Progress bar */}
        <div style={{
          marginTop: 14,
          height: 4,
          borderRadius: 2,
          backgroundColor: 'rgba(255,255,255,0.2)',
          overflow: 'hidden',
        }}>
          <div
            className="animate-pulse"
            style={{
              height: '100%',
              borderRadius: 2,
              backgroundColor: 'rgba(255,255,255,0.7)',
              width: taskStatus === 'layout' ? '20%'
                : taskStatus === 'ocr' ? '45%'
                : taskStatus === 'security' ? '65%'
                : taskStatus === 'readying' ? '85%'
                : '10%',
              transition: 'width 0.5s ease',
            }}
          />
        </div>
      </div>
    </div>
  ) : null

  // Spreadsheet viewer for CSV / Excel
  if (isSpreadsheet) {
    return <SpreadsheetViewer docUuid={docUuid} processing={processing} taskStatus={taskStatus} />
  }

  // Loading state
  if (isPdf === null) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative' }}>
        {processingOverlay}
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#525659' }}>
          <div style={{ color: '#9ca3af', fontSize: 14 }}>Loading document...</div>
        </div>
      </div>
    )
  }

  // Non-PDF fallback: iframe
  if (!isPdf) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative' }}>
        {processingOverlay}
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
          <button onClick={() => window.open(url, '_blank')} style={btnStyle} title="Open in new tab">
            <Maximize2 size={16} />
          </button>
        </div>
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
              src={url}
              style={{ width: '100%', height: '100%', border: 'none' }}
              title="Document viewer"
            />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative' }}>
      {processingOverlay}

      {/* Toolbar */}
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
        <button onClick={() => window.open(url, '_blank')} style={btnStyle} title="Open in new tab">
          <Maximize2 size={16} />
        </button>
      </div>

      {/* PDF pages container */}
      <div style={{
        flex: 1, overflow: 'auto', backgroundColor: '#525659',
        position: 'relative',
      }}>
        <div ref={containerRef} style={{ paddingBottom: 20 }} />

        {/* Highlight navigation bar */}
        {totalHighlights > 0 && (
          <div style={{
            position: 'sticky',
            bottom: 12,
            left: 0,
            right: 0,
            margin: '0 24px',
            height: 48,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '0 8px',
            borderRadius: 10,
            border: '1px solid #e5e7eb',
            backdropFilter: 'blur(12px)',
            backgroundColor: 'rgba(255,255,255,0.85)',
            boxShadow: '0 2px 12px rgba(0,0,0,0.12)',
            zIndex: 100,
          }}>
            <button
              onClick={() => goToHighlight('prev')}
              style={{
                ...btnStyle,
                width: 34, height: 34,
                border: 'none',
                background: 'none',
              }}
              title="Previous highlight"
            >
              <ChevronLeft size={18} />
            </button>
            <div style={{
              flex: 1,
              textAlign: 'center',
              fontSize: 14,
              color: '#374151',
              overflow: 'hidden',
              whiteSpace: 'nowrap',
              textOverflow: 'ellipsis',
            }}>
              <span style={{ fontWeight: 700 }}>
                &ldquo;{highlightTerms[0]}&rdquo;
              </span>
              <span style={{ marginLeft: 6, color: '#9ca3af', fontWeight: 400 }}>
                {currentHighlight + 1} of {totalHighlights}
              </span>
            </div>
            <button
              onClick={() => goToHighlight('next')}
              style={{
                ...btnStyle,
                width: 34, height: 34,
                border: 'none',
                background: 'none',
              }}
              title="Next highlight"
            >
              <ChevronRight size={18} />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
