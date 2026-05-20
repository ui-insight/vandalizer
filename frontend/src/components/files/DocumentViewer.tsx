import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ZoomIn, ZoomOut, Maximize2, ChevronLeft, ChevronRight, Loader2, X, Search, AlertCircle, RefreshCw } from 'lucide-react'
import { downloadFileUrl } from '../../api/files'
import { pollStatus, retryExtraction } from '../../api/documents'
import { SpreadsheetViewer } from './SpreadsheetViewer'
import { DocumentSearchBar, useFindInDocumentHotkey } from './DocumentSearchBar'
import { stageCopy } from '../../utils/processingStatus'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import * as pdfjsLib from 'pdfjs-dist/legacy/build/pdf.mjs'
import pdfjsWorker from 'pdfjs-dist/legacy/build/pdf.worker.mjs?url'

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker

interface DocumentViewerProps {
  docUuid: string
  highlightTerms?: string[]
  onClearHighlights?: () => void
  processing?: boolean
  taskStatus?: string | null
}

const ZOOM_LEVELS = [0.5, 0.75, 1, 1.25, 1.5, 2]
const HIGHLIGHT_COLOR = '#eab308'

// Drive pdfjs's text stream with an explicit reader loop. Avoids
// `for await..of` on a ReadableStream, which throws on Safari versions
// lacking ReadableStream[Symbol.asyncIterator].
async function readTextItems(page: pdfjsLib.PDFPageProxy): Promise<unknown[]> {
  const stream = (page as unknown as { streamTextContent: () => ReadableStream }).streamTextContent()
  const reader = stream.getReader()
  const items: unknown[] = []
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      const chunkItems = (value as { items?: unknown[] } | undefined)?.items
      if (chunkItems && chunkItems.length > 0) items.push(...chunkItems)
    }
  } finally {
    try { reader.releaseLock() } catch { /* noop */ }
  }
  return items
}

// Walk text nodes under `root`, wrap occurrences of `query` (case-insensitive,
// whole-text-node only — no cross-node matching) in <mark.doc-search-hl>.
// Returns the number of matches inserted. Idempotent: prior marks from this
// helper are unwrapped first.
function highlightHtmlSearch(root: HTMLElement, query: string): number {
  // Unwrap prior marks
  const prior = root.querySelectorAll('mark.doc-search-hl')
  prior.forEach(mark => {
    const parent = mark.parentNode
    if (!parent) return
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark)
    parent.removeChild(mark)
  })
  // Coalesce adjacent text nodes left behind by the unwrap
  prior.forEach(mark => {
    const p = mark.parentNode as Element | null
    if (p && typeof p.normalize === 'function') p.normalize()
  })

  const trimmed = query.trim()
  if (!trimmed) return 0
  const needle = trimmed.toLowerCase()
  const needleLen = needle.length

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) => {
      const parent = node.parentElement
      if (!parent) return NodeFilter.FILTER_REJECT
      const tag = parent.tagName
      if (tag === 'SCRIPT' || tag === 'STYLE') return NodeFilter.FILTER_REJECT
      return NodeFilter.FILTER_ACCEPT
    },
  })
  const nodes: Text[] = []
  let n: Node | null
  while ((n = walker.nextNode())) nodes.push(n as Text)

  let count = 0
  for (const node of nodes) {
    const text = node.nodeValue || ''
    const lower = text.toLowerCase()
    if (!lower.includes(needle)) continue

    const frag = document.createDocumentFragment()
    let cursor = 0
    let from = 0
    while (from < lower.length) {
      const idx = lower.indexOf(needle, from)
      if (idx === -1) break
      if (idx > cursor) frag.appendChild(document.createTextNode(text.slice(cursor, idx)))
      const mark = document.createElement('mark')
      mark.className = 'doc-search-hl'
      mark.dataset.searchIdx = String(count)
      mark.style.backgroundColor = '#fde68a'
      mark.style.color = 'inherit'
      mark.style.padding = '0'
      mark.style.borderRadius = '2px'
      mark.appendChild(document.createTextNode(text.slice(idx, idx + needleLen)))
      frag.appendChild(mark)
      cursor = idx + needleLen
      from = cursor
      count++
    }
    if (cursor < text.length) frag.appendChild(document.createTextNode(text.slice(cursor)))
    node.parentNode?.replaceChild(frag, node)
  }
  return count
}

export function DocumentViewer({ docUuid, highlightTerms = [], onClearHighlights, processing, taskStatus }: DocumentViewerProps) {
  const [zoom, setZoom] = useState(2) // index into ZOOM_LEVELS, default 100%
  const [isPdf, setIsPdf] = useState<boolean | null>(null) // null = loading
  const [isSpreadsheet, setIsSpreadsheet] = useState(false)
  const [isDocx, setIsDocx] = useState(false)
  const [docxText, setDocxText] = useState<string | null>(null)
  const [extractionError, setExtractionError] = useState<string | null>(null)
  const [retrying, setRetrying] = useState(false)
  const [blobUrl, setBlobUrl] = useState<string | null>(null) // for non-PDF iframe fallback
  const containerRef = useRef<HTMLDivElement>(null)
  const pdfDocRef = useRef<pdfjsLib.PDFDocumentProxy | null>(null)
  const renderingRef = useRef(false)
  const [totalHighlights, setTotalHighlights] = useState(0)
  const [currentHighlight, setCurrentHighlight] = useState(0)

  // In-document find (Cmd/Ctrl+F)
  const rootRef = useRef<HTMLDivElement>(null)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const docxContentRef = useRef<HTMLDivElement>(null)
  const [docxMatchCount, setDocxMatchCount] = useState(0)
  const [docxCurrentMatch, setDocxCurrentMatch] = useState(0)

  const zoomLevel = ZOOM_LEVELS[zoom]
  // Two URLs for the same file:
  //  - `inlineUrl` asks the server to serve with `Content-Disposition: inline`
  //    so the browser will render the file (used by PDF.js and "open in tab").
  //  - `downloadUrl` retains the default `attachment` disposition for the
  //    user-facing Download button.
  const inlineUrl = downloadFileUrl(docUuid, { inline: true })
  const downloadUrl = downloadFileUrl(docUuid)

  const openSearch = useCallback(() => setSearchOpen(true), [])
  const closeSearch = useCallback(() => {
    setSearchOpen(false)
    setSearchQuery('')
  }, [])

  useFindInDocumentHotkey(rootRef, searchOpen, openSearch, closeSearch)

  // When the user types into the find bar, the typed query takes priority
  // over extraction-driven highlights. Closing the bar restores them.
  const effectiveTerms = useMemo(() => {
    if (searchOpen) {
      const q = searchQuery.trim()
      return q ? [q] : []
    }
    return highlightTerms
  }, [searchOpen, searchQuery, highlightTerms])

  // Detect file type, then route to the right loader.
  //
  // For PDFs we deliberately skip pre-fetching the bytes: a HEAD picks the
  // type, then pdfjs streams pages via byte-range requests as the user
  // scrolls (the backend serves `Accept-Ranges: bytes`). For a 20 MB file
  // this paints the first page in seconds instead of waiting for the full
  // body to land.
  useEffect(() => {
    let cancelled = false
    let createdBlobUrl: string | null = null
    setIsPdf(null)
    setIsSpreadsheet(false)
    setIsDocx(false)
    setDocxText(null)
    setBlobUrl(null)

    fetch(inlineUrl, { method: 'HEAD', credentials: 'include' })
      .then(async (resp) => {
        if (cancelled) return
        const ct = resp.headers.get('content-type') || ''
        if (ct.includes('csv') || ct.includes('spreadsheet') || ct.includes('excel') || ct.includes('ms-excel')) {
          setIsSpreadsheet(true)
          setIsPdf(false)
        } else if (ct.includes('pdf')) {
          // PDF.js loads progressively from the URL — no full-body fetch
          setIsPdf(true)
        } else if (
          ct.includes('wordprocessingml') ||
          ct.includes('msword') ||
          ct.includes('markdown') ||
          ct.includes('text/plain')
        ) {
          setIsDocx(true)
          setIsPdf(false)
          pollStatus(docUuid).then(res => {
            if (cancelled) return
            if (res.status === 'error' || (res.complete && !res.raw_text)) {
              setExtractionError(res.error_message || "We couldn't extract any text from this document.")
              setDocxText('')
            } else {
              setExtractionError(null)
              setDocxText(res.raw_text || '')
            }
          }).catch(() => {
            if (!cancelled) setDocxText('')
          })
        } else {
          // Generic fallback: fetch into a blob URL so the iframe inherits
          // browser-side caching and doesn't need a second auth round-trip.
          const fullResp = await fetch(inlineUrl, { credentials: 'include' })
          if (cancelled) return
          const blob = await fullResp.blob()
          if (cancelled) return
          createdBlobUrl = URL.createObjectURL(blob)
          setBlobUrl(createdBlobUrl)
          setIsPdf(false)
        }
      })
      .catch(() => {
        if (!cancelled) setIsPdf(false)
      })

    return () => {
      cancelled = true
      if (createdBlobUrl) URL.revokeObjectURL(createdBlobUrl)
    }
  }, [inlineUrl, docUuid])

  // Re-fetch docx text when processing completes
  useEffect(() => {
    if (!isDocx || processing) return
    let cancelled = false
    pollStatus(docUuid).then(res => {
      if (cancelled) return
      if (res.status === 'error' || (res.complete && !res.raw_text)) {
        setExtractionError(res.error_message || "We couldn't extract any text from this document.")
        setDocxText('')
      } else {
        setExtractionError(null)
        setDocxText(res.raw_text || '')
      }
    }).catch(() => {})
    return () => { cancelled = true }
  }, [isDocx, processing, docUuid])

  const handleRetryExtraction = useCallback(async () => {
    setRetrying(true)
    setExtractionError(null)
    try {
      await retryExtraction(docUuid)
      setDocxText(null) // back to loading state
      // Poll for completion every 3s.
      const interval = window.setInterval(async () => {
        try {
          const res = await pollStatus(docUuid)
          if (res.complete || (!res.processing && res.status !== 'extracting' && res.status !== 'readying')) {
            window.clearInterval(interval)
            if (res.status === 'error' || (res.complete && !res.raw_text)) {
              setExtractionError(res.error_message || "We couldn't extract any text from this document.")
              setDocxText('')
            } else {
              setDocxText(res.raw_text || '')
            }
            setRetrying(false)
          }
        } catch {
          window.clearInterval(interval)
          setRetrying(false)
        }
      }, 3000)
    } catch (err) {
      setExtractionError(err instanceof Error ? err.message : 'Retry failed.')
      setRetrying(false)
    }
  }, [docUuid])

  // Load PDF document by streaming from the server. pdfjs issues byte-range
  // requests under the hood so we don't block on the full file; pages render
  // as they arrive instead of after a multi-minute arrayBuffer wait.
  useEffect(() => {
    if (isPdf !== true) return
    let cancelled = false

    const loadTask = pdfjsLib.getDocument({
      url: inlineUrl,
      withCredentials: true,
    })
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
  }, [isPdf, inlineUrl])

  // Re-render pages when zoom changes
  useEffect(() => {
    if (isPdf !== true || !pdfDocRef.current) return
    renderAllPages(pdfDocRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoomLevel])

  // Re-apply highlights when terms change
  useEffect(() => {
    if (isPdf !== true || !pdfDocRef.current) return
    applyHighlights(pdfDocRef.current, effectiveTerms).catch(err => {
      console.error('[DocumentViewer] applyHighlights failed:', err)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveTerms])

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
        canvas,
        canvasContext: ctx,
        viewport,
        transform: [dpr, 0, 0, dpr, 0, 0],
      }).promise
    }

    renderingRef.current = false

    // Apply highlights after rendering
    if (effectiveTerms.length > 0) {
      applyHighlights(doc, effectiveTerms).catch(err => {
        console.error('[DocumentViewer] applyHighlights failed:', err)
      })
    }
  }, [zoomLevel, effectiveTerms])

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

    // PDFs break runs of text into many TextItems — a single visible phrase like
    // "University of Idaho" can span 1..N items. So instead of substring-matching
    // against each item independently, we concatenate the page's text into one
    // string (with a space between items so adjacent tokens don't fuse) and
    // keep a parallel map from each char position back to (itemIdx, localIdx).
    // We then search in the concatenated string and project matches back to
    // per-item rectangles.
    type TextItem = { str: string; transform: number[]; width: number; height: number }
    type CharRef = { itemIdx: number; localIdx: number } | null

    let matchCount = 0

    for (let i = 1; i <= doc.numPages; i++) {
      const page = await doc.getPage(i)
      const viewport = page.getViewport({ scale: zoomLevel })
      // pdfjs's built-in getTextContent() uses `for await..of` on a
      // ReadableStream, which throws on Safari versions that don't implement
      // ReadableStream[Symbol.asyncIterator]. Drive the stream by hand.
      const textItems = await readTextItems(page)
      const wrapper = container.querySelector(`[data-page-num="${i}"]`)
      const overlay = wrapper?.querySelector('.pdf-overlay')
      if (!overlay) continue

      const items: TextItem[] = []
      for (const raw of textItems) {
        if (raw && typeof raw === 'object' && 'str' in raw) items.push(raw as TextItem)
      }

      const charRefs: CharRef[] = []
      let concat = ''
      for (let idx = 0; idx < items.length; idx++) {
        const s = items[idx].str
        for (let j = 0; j < s.length; j++) {
          charRefs.push({ itemIdx: idx, localIdx: j })
          concat += s[j]
        }
        if (s.length > 0 && idx < items.length - 1) {
          charRefs.push(null) // separator — not part of any item
          concat += ' '
        }
      }
      const concatLower = concat.toLowerCase()

      for (const term of terms) {
        if (!term) continue
        // Collapse internal whitespace in the search term so multi-word values
        // match regardless of exactly where the PDF broke the runs.
        const termLower = term.toLowerCase().replace(/\s+/g, ' ').trim()
        if (!termLower) continue

        let from = 0
        while (from < concatLower.length) {
          const matchStart = concatLower.indexOf(termLower, from)
          if (matchStart === -1) break
          const matchEnd = matchStart + termLower.length
          from = matchStart + 1

          // Gather the span of each item that is covered by this match.
          const perItem = new Map<number, { start: number; end: number }>()
          for (let k = matchStart; k < matchEnd; k++) {
            const ref = charRefs[k]
            if (!ref) continue
            const existing = perItem.get(ref.itemIdx)
            if (!existing) {
              perItem.set(ref.itemIdx, { start: ref.localIdx, end: ref.localIdx })
            } else {
              if (ref.localIdx < existing.start) existing.start = ref.localIdx
              if (ref.localIdx > existing.end) existing.end = ref.localIdx
            }
          }

          for (const [itemIdx, span] of perItem) {
            const textItem = items[itemIdx]
            const textStr = textItem.str
            if (!textStr) continue

            const fontHeight = Math.sqrt(
              textItem.transform[2] * textItem.transform[2] +
              textItem.transform[3] * textItem.transform[3]
            ) || textItem.height || 10

            const tx = textItem.transform[4]
            const ty = textItem.transform[5]

            const vt = viewport.transform
            const vpX = vt[0] * tx + vt[2] * ty + vt[4]
            const vpY = vt[1] * tx + vt[3] * ty + vt[5]
            const fontHeightVp = fontHeight * viewport.scale

            const fullWidth = textItem.width * viewport.scale
            const charCount = textStr.length
            const xOffset = charCount > 0 ? (span.start / charCount) * fullWidth : 0
            const matchLen = span.end - span.start + 1
            const matchWidth = charCount > 0 ? (matchLen / charCount) * fullWidth : fullWidth

            const hl = document.createElement('div')
            hl.className = 'pdf-highlight'
            hl.dataset.highlightIndex = String(matchCount)
            Object.assign(hl.style, {
              position: 'absolute',
              left: `${vpX + xOffset}px`,
              top: `${vpY - fontHeightVp}px`,
              width: `${matchWidth}px`,
              height: `${fontHeightVp}px`,
              backgroundColor: HIGHLIGHT_COLOR,
              opacity: '0.45',
              pointerEvents: 'none',
              borderRadius: '2px',
            })
            overlay.appendChild(hl)
          }

          matchCount++
        }
      }

      // Also search AcroForm / widget annotations — form-field values don't
      // appear in the page's text layer, but many extractions pull from them.
      try {
        const annotations = await page.getAnnotations()
        for (const ann of annotations) {
          const a = ann as { subtype?: string; fieldType?: string; fieldValue?: unknown; rect?: number[] }
          if (a.subtype !== 'Widget' || a.fieldType !== 'Tx') continue
          const rawValue = a.fieldValue
          if (rawValue === undefined || rawValue === null) continue
          const fieldVal = Array.isArray(rawValue) ? rawValue.join(' ') : String(rawValue)
          const fieldLower = fieldVal.toLowerCase().replace(/\s+/g, ' ').trim()
          if (!fieldLower || !a.rect || a.rect.length < 4) continue

          for (const term of terms) {
            if (!term) continue
            const termLower = term.toLowerCase().replace(/\s+/g, ' ').trim()
            if (!termLower || !fieldLower.includes(termLower)) continue

            const [vx1, vy1, vx2, vy2] = viewport.convertToViewportRectangle(a.rect)
            const left = Math.min(vx1, vx2)
            const top = Math.min(vy1, vy2)
            const width = Math.abs(vx2 - vx1)
            const height = Math.abs(vy2 - vy1)
            if (width <= 0 || height <= 0) continue

            const hl = document.createElement('div')
            hl.className = 'pdf-highlight'
            hl.dataset.highlightIndex = String(matchCount)
            Object.assign(hl.style, {
              position: 'absolute',
              left: `${left}px`,
              top: `${top}px`,
              width: `${width}px`,
              height: `${height}px`,
              backgroundColor: HIGHLIGHT_COLOR,
              opacity: '0.45',
              pointerEvents: 'none',
              borderRadius: '2px',
            })
            overlay.appendChild(hl)
            matchCount++
            break // one hit per field is enough
          }
        }
      } catch (err) {
        console.warn('[DocumentViewer] annotation search failed:', err)
      }
    }

    setTotalHighlights(matchCount)
    if (matchCount > 0) {
      setCurrentHighlight(0)
      // Double rAF ensures DOM layout is complete before scrolling
      requestAnimationFrame(() => {
        requestAnimationFrame(() => scrollToHighlightByIndex(0))
      })
    }
  }, [zoomLevel])

  const scrollToHighlightByIndex = (index: number) => {
    const container = containerRef.current
    if (!container) return

    const allHighlights = container.querySelectorAll('.pdf-highlight')
    if (allHighlights.length === 0) return

    // A single match may have multiple rects (cross-text-item). Update opacity
    // by match index and scroll to the first rect of the active match.
    allHighlights.forEach((hl) => {
      const el = hl as HTMLElement
      const idx = Number(el.dataset.highlightIndex)
      el.style.opacity = idx === index ? '0.75' : '0.45'
    })

    const target = container.querySelector(
      `.pdf-highlight[data-highlight-index="${index}"]`
    ) as HTMLElement | null
    if (!target) return

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
      requestAnimationFrame(() => scrollToHighlightByIndex(next))
      return next
    })
  }, [totalHighlights])

  // ----- DOCX/HTML search wiring -----

  const scrollDocxMatch = useCallback((index: number) => {
    const root = docxContentRef.current
    if (!root) return
    root.querySelectorAll<HTMLElement>('mark.doc-search-hl').forEach((el) => {
      const idx = Number(el.dataset.searchIdx)
      el.style.backgroundColor = idx === index ? '#fbbf24' : '#fde68a'
      el.style.outline = idx === index ? '2px solid #f59e0b' : 'none'
    })
    const target = root.querySelector<HTMLElement>(
      `mark.doc-search-hl[data-search-idx="${index}"]`,
    )
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [])

  // Re-apply DOCX highlights when the query changes or the rendered HTML
  // is replaced (e.g. text re-poll after processing).
  useEffect(() => {
    if (!isDocx) return
    const root = docxContentRef.current
    if (!root) return
    const q = searchOpen ? searchQuery : ''
    const count = highlightHtmlSearch(root, q)
    setDocxMatchCount(count)
    setDocxCurrentMatch(0)
    if (count > 0) {
      requestAnimationFrame(() => scrollDocxMatch(0))
    }
  }, [isDocx, searchOpen, searchQuery, docxText, scrollDocxMatch])

  const goToDocxMatch = useCallback((direction: 'next' | 'prev') => {
    if (docxMatchCount === 0) return
    setDocxCurrentMatch(prev => {
      const next = direction === 'next'
        ? (prev + 1 >= docxMatchCount ? 0 : prev + 1)
        : (prev - 1 < 0 ? docxMatchCount - 1 : prev - 1)
      requestAnimationFrame(() => scrollDocxMatch(next))
      return next
    })
  }, [docxMatchCount, scrollDocxMatch])

  const zoomIn = useCallback(() => {
    setZoom(prev => Math.min(prev + 1, ZOOM_LEVELS.length - 1))
  }, [])

  const zoomOut = useCallback(() => {
    setZoom(prev => Math.max(prev - 1, 0))
  }, [])

  const resetZoom = useCallback(() => {
    setZoom(2)
  }, [])

  // The download endpoint serves `inline` disposition when `?inline=1` is set,
  // so the browser renders the PDF in the new tab instead of downloading it.
  const openPdfInNewTab = useCallback(() => {
    window.open(inlineUrl, '_blank')
  }, [inlineUrl])

  const btnStyle: React.CSSProperties = {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: 32, height: 32, borderRadius: 6, border: '1px solid #d1d5db',
    background: '#fff', cursor: 'pointer', color: '#374151',
    fontSize: 13, fontWeight: 500,
  }

  // Processing overlay - shown when document is still being processed
  const processingOverlay = processing ? (
    <div
      aria-live="polite"
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 50,
        display: 'flex',
        justifyContent: 'center',
        padding: '20px 24px',
      }}
    >
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
              {stageCopy(taskStatus).title}
            </div>
            <div style={{ fontSize: 12, opacity: 0.8, marginTop: 3 }}>
              {stageCopy(taskStatus).message}
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
              width: `${Math.round(stageCopy(taskStatus).progress * 100)}%`,
              transition: 'width 0.5s ease',
            }}
          />
        </div>
      </div>
    </div>
  ) : null

  // DOCX rendered HTML (must be before conditional returns for hooks rules)
  const docxHtml = useMemo(() => {
    if (!docxText) return ''
    return DOMPurify.sanitize(marked.parse(docxText) as string)
  }, [docxText])

  // Spreadsheet viewer for CSV / Excel
  if (isSpreadsheet) {
    return <SpreadsheetViewer docUuid={docUuid} processing={processing} taskStatus={taskStatus} />
  }

  // DOCX rendered markdown viewer
  if (isDocx) {
    return (
      <div ref={rootRef} style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative' }}>
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
          <button onClick={openSearch} style={btnStyle} title="Find in document (⌘F / Ctrl+F)" aria-label="Find in document">
            <Search size={16} />
          </button>
          <button onClick={() => window.open(downloadUrl, '_blank')} style={btnStyle} title="Download original">
            <Maximize2 size={16} />
          </button>
        </div>
        {searchOpen && (
          <DocumentSearchBar
            query={searchQuery}
            onQueryChange={setSearchQuery}
            currentMatch={docxMatchCount === 0 ? 0 : docxCurrentMatch + 1}
            totalMatches={docxMatchCount}
            onPrev={() => goToDocxMatch('prev')}
            onNext={() => goToDocxMatch('next')}
            onClose={closeSearch}
            autoFocus
          />
        )}
        <div style={{
          flex: 1, overflow: 'auto', backgroundColor: '#fff', position: 'relative',
        }}>
          {docxText === null ? (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
              <Loader2 style={{ width: 32, height: 32, color: 'var(--highlight-color)', animation: 'spin 1s linear infinite' }} />
            </div>
          ) : extractionError ? (
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              gap: 16, padding: 32, height: '100%', textAlign: 'center',
            }}>
              <AlertCircle style={{ width: 40, height: 40, color: '#dc2626' }} />
              <div style={{ fontSize: 15, fontWeight: 600, color: '#111' }}>
                Text extraction failed
              </div>
              <div style={{ fontSize: 14, color: '#555', maxWidth: 480, lineHeight: 1.5 }}>
                {extractionError}
              </div>
              <button
                onClick={handleRetryExtraction}
                disabled={retrying}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '8px 14px', fontSize: 14, fontWeight: 500,
                  backgroundColor: retrying ? '#9ca3af' : 'var(--highlight-color)',
                  color: '#fff', border: 'none', borderRadius: 6,
                  cursor: retrying ? 'not-allowed' : 'pointer',
                }}
              >
                <RefreshCw
                  style={{
                    width: 14, height: 14,
                    animation: retrying ? 'spin 1s linear infinite' : undefined,
                  }}
                />
                {retrying ? 'Retrying...' : 'Retry extraction'}
              </button>
            </div>
          ) : (
            <div style={{
              padding: '32px 48px',
              maxWidth: 800,
              margin: '0 auto',
              fontSize: `${14 * zoomLevel}px`,
              lineHeight: 1.7,
              color: '#333',
            }}>
              <div
                ref={docxContentRef}
                className="chat-markdown"
                dangerouslySetInnerHTML={{ __html: docxHtml }}
              />
            </div>
          )}
        </div>
      </div>
    )
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
          <button
            onClick={() => { if (blobUrl) window.open(blobUrl, '_blank') }}
            style={btnStyle}
            title="Open in new tab"
            disabled={!blobUrl}
          >
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
            {blobUrl ? (
              <iframe
                src={blobUrl}
                style={{ width: '100%', height: '100%', border: 'none' }}
                title="Document viewer"
              />
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#9ca3af', fontSize: 13 }}>
                Loading...
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div ref={rootRef} style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative' }}>
      {processingOverlay}

      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
        padding: '6px 12px', borderBottom: '1px solid #e5e7eb', backgroundColor: '#f9fafb',
        flexShrink: 0,
      }}>
        <button onClick={zoomOut} style={btnStyle} title="Zoom out" aria-label="Zoom out" disabled={zoom <= 0}>
          <ZoomOut size={16} />
        </button>
        <button onClick={resetZoom} style={{ ...btnStyle, width: 'auto', padding: '0 10px' }} title="Reset zoom" aria-label="Reset zoom">
          {Math.round(zoomLevel * 100)}%
        </button>
        <button onClick={zoomIn} style={btnStyle} title="Zoom in" aria-label="Zoom in" disabled={zoom >= ZOOM_LEVELS.length - 1}>
          <ZoomIn size={16} />
        </button>
        <div style={{ width: 1, height: 20, backgroundColor: '#d1d5db', margin: '0 4px' }} />
        <button onClick={openSearch} style={btnStyle} title="Find in document (⌘F / Ctrl+F)" aria-label="Find in document">
          <Search size={16} />
        </button>
        <button onClick={openPdfInNewTab} style={btnStyle} title="Open in new tab" aria-label="Open in new tab">
          <Maximize2 size={16} />
        </button>
      </div>

      {searchOpen && (
        <DocumentSearchBar
          query={searchQuery}
          onQueryChange={setSearchQuery}
          currentMatch={totalHighlights === 0 ? 0 : currentHighlight + 1}
          totalMatches={totalHighlights}
          onPrev={() => goToHighlight('prev')}
          onNext={() => goToHighlight('next')}
          onClose={closeSearch}
          autoFocus
        />
      )}

      {/* PDF pages container */}
      <div style={{
        flex: 1, overflow: 'auto', backgroundColor: '#525659',
        position: 'relative',
      }}>
        <div ref={containerRef} style={{ paddingBottom: 20 }} />

        {/* Highlight navigation bar */}
        {!searchOpen && totalHighlights > 0 && (
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
              aria-label="Previous highlight"
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
                &ldquo;{effectiveTerms[0]}&rdquo;
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
              aria-label="Next highlight"
            >
              <ChevronRight size={18} />
            </button>
            {onClearHighlights && (
              <button
                onClick={onClearHighlights}
                style={{
                  ...btnStyle,
                  width: 34, height: 34,
                  border: 'none',
                  background: 'none',
                }}
                title="Clear highlights"
                aria-label="Clear highlights"
              >
                <X size={18} />
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
