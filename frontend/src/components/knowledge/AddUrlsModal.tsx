import { useEffect, useRef, useState } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { X } from 'lucide-react'
import * as api from '../../api/knowledge'
import type { CrawlPreview } from '../../api/knowledge'
import { CrawlPreviewStep } from './CrawlPreviewStep'
import { defaultSelection } from './crawlPreview'

interface AddUrlsModalProps {
  kbUuid: string
  onSubmit: (urls: string[], crawlEnabled: boolean, maxCrawlPages: number, allowedDomains: string) => void
  /** A crawl's ticked pages were queued for adding (crawl previews add
   *  through their own endpoint, not ``onSubmit``). */
  onCrawlAdded: (added: number) => void
  onClose: () => void
}

const POLL_MS = 1500

export function AddUrlsModal({ kbUuid, onSubmit, onCrawlAdded, onClose }: AddUrlsModalProps) {
  const [text, setText] = useState('')
  const [crawlEnabled, setCrawlEnabled] = useState(false)
  const [maxCrawlPages, setMaxCrawlPages] = useState(5)
  const [allowedDomains, setAllowedDomains] = useState('')

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Ref, not state: a double-click's second event can fire before React
  // re-renders the disabled button, and two POSTs enqueue two ingest runs
  // that race each other (the duplicate-source support ticket).
  const submittedRef = useRef(false)
  const [submitted, setSubmitted] = useState(false)

  // Crawling is a dry run first: the crawl's pages are found and listed, and
  // only the ones ticked are added. Without crawling, Add URLs adds directly.
  const [preview, setPreview] = useState<CrawlPreview | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const seenRef = useRef<Set<string>>(new Set())

  const enteredUrls = () => text
    .split('\n')
    .map(u => u.trim())
    .filter(u => u.length > 0)

  const handleSubmit = () => {
    if (submittedRef.current) return
    const urls = enteredUrls()
    if (urls.length === 0) return
    submittedRef.current = true
    setSubmitted(true)
    if (!crawlEnabled) {
      onSubmit(urls, false, maxCrawlPages, allowedDomains)
      return
    }
    setPreviewError(null)
    seenRef.current = new Set()
    setSelected(new Set())
    api.startCrawlPreview(kbUuid, urls, maxCrawlPages, allowedDomains)
      .then(p => setPreview(p))
      .catch(err => setPreviewError(err instanceof Error ? err.message : 'Could not start finding pages'))
      .finally(() => { submittedRef.current = false; setSubmitted(false) })
  }

  // Poll a running preview; pages appear as they are found.
  const previewUuid = preview?.uuid
  const previewRunning = preview?.status === 'running'
  useEffect(() => {
    if (!previewUuid || !previewRunning) return
    const t = setInterval(() => {
      api.getCrawlPreview(kbUuid, previewUuid)
        .then(p => setPreview(p))
        .catch(err => setPreviewError(err instanceof Error ? err.message : 'Lost track of the crawl preview'))
    }, POLL_MS)
    return () => clearInterval(t)
  }, [kbUuid, previewUuid, previewRunning])

  // A page newly found gets its default tick; one the user already changed
  // keeps their choice.
  const previewPages = preview?.pages
  useEffect(() => {
    if (!previewPages) return
    const fresh = previewPages.filter(p => !seenRef.current.has(p.url))
    if (fresh.length === 0) return
    for (const p of fresh) seenRef.current.add(p.url)
    const ticks = defaultSelection(fresh)
    if (ticks.size) setSelected(prev => new Set([...prev, ...ticks]))
  }, [previewPages])

  const addingRef = useRef(false)
  const [adding, setAdding] = useState(false)
  const handleAddSelected = () => {
    if (!preview || addingRef.current || selected.size === 0) return
    addingRef.current = true
    setAdding(true)
    api.addCrawlPreviewSelection(kbUuid, preview.uuid, [...selected])
      .then(r => onCrawlAdded(r.added))
      .catch(err => {
        addingRef.current = false
        setAdding(false)
        setPreviewError(err instanceof Error ? err.message : 'Failed to add the selected pages')
      })
  }


  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        backgroundColor: 'rgba(0,0,0,0.6)',
      }}
      onClick={onClose}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        role="dialog"
        aria-modal="true"
        style={{
          width: preview ? 640 : 480, maxWidth: '100vw', maxHeight: '80vh',
          backgroundColor: '#1e1e1e', borderRadius: 12,
          border: '1px solid #3a3a3a', padding: 24,
          display: 'flex', flexDirection: 'column', gap: 16,
          overflowY: 'auto',
        }}
        onClick={e => e.stopPropagation()}
      >
        {preview ? (
          <CrawlPreviewStep
            preview={preview}
            selected={selected}
            onChange={setSelected}
            error={previewError}
            adding={adding}
            onAdd={handleAddSelected}
            onBack={() => { setPreview(null); setPreviewError(null) }}
            onClose={onClose}
          />
        ) : (<>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 16, fontWeight: 600, color: '#fff' }}>Add URLs</span>
          <button
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 4, display: 'flex' }}
          >
            <X size={18} style={{ color: '#888' }} />
          </button>
        </div>
        <div style={{ fontSize: 13, color: '#aaa' }}>
          Paste one URL per line. Each URL will be fetched, its text extracted, and added to the knowledge base.
        </div>
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          aria-label="URLs to add, one per line"
          placeholder={'https://example.com/page1\nhttps://example.com/page2'}
          rows={8}
          style={{
            width: '100%', padding: 12, fontSize: 13, fontFamily: 'inherit',
            backgroundColor: '#2a2a2a', color: '#e5e5e5',
            border: '1px solid #3a3a3a', borderRadius: 8,
            resize: 'vertical',
          }}
        />

        {/* Crawl toggle */}
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={crawlEnabled}
            onChange={e => setCrawlEnabled(e.target.checked)}
            style={{ accentColor: 'var(--highlight-color, #eab308)' }}
          />
          <span style={{ fontSize: 13, color: '#e5e5e5' }}>Enable crawling</span>
        </label>

        {crawlEnabled && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingLeft: 4 }}>
            <div style={{ fontSize: 12, color: '#888', lineHeight: 1.5 }}>
              The crawler will follow links on each page — including links embedded in PDFs — and list the pages it finds.
              Nothing is added until you choose which of them to include.
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <label htmlFor="add-urls-max-pages" style={{ fontSize: 13, color: '#aaa', minWidth: 80 }}>Max pages</label>
              <input
                id="add-urls-max-pages"
                type="number"
                value={maxCrawlPages}
                onChange={e => setMaxCrawlPages(Math.max(1, Math.min(50, parseInt(e.target.value) || 1)))}
                min={1}
                max={50}
                style={{
                  width: 72, padding: '6px 8px', fontSize: 13, fontFamily: 'inherit',
                  backgroundColor: '#2a2a2a', color: '#e5e5e5',
                  border: '1px solid #3a3a3a', borderRadius: 6,
                }}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label htmlFor="add-urls-allowed-domains" style={{ fontSize: 13, color: '#aaa' }}>Allowed domains (optional)</label>
              <input
                id="add-urls-allowed-domains"
                type="text"
                value={allowedDomains}
                onChange={e => setAllowedDomains(e.target.value)}
                placeholder="example.com, example.com/section"
                style={{
                  width: '100%', padding: '6px 8px', fontSize: 13, fontFamily: 'inherit',
                  backgroundColor: '#2a2a2a', color: '#e5e5e5',
                  border: '1px solid #3a3a3a', borderRadius: 6,
                }}
              />
              <div style={{ fontSize: 11, color: '#666' }}>
                Comma-separated. Include a path (e.g. example.com/irb) to limit the crawl
                to that section of the site. Defaults to the same domain as the URL.
              </div>
            </div>
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 16px', fontSize: 13, fontWeight: 500, fontFamily: 'inherit',
              color: '#ccc', backgroundColor: 'transparent',
              border: '1px solid #3a3a3a', borderRadius: 6, cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!text.trim() || submitted}
            style={{
              padding: '8px 16px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
              color: 'var(--highlight-text-color, #000)', backgroundColor: 'var(--highlight-color, #eab308)',
              border: 'none', borderRadius: 6,
              cursor: text.trim() && !submitted ? 'pointer' : 'default',
              opacity: text.trim() && !submitted ? 1 : 0.5,
            }}
          >
            {crawlEnabled
              ? (submitted ? 'Starting…' : 'Find pages')
              : (submitted ? 'Adding…' : 'Add URLs')}
          </button>
        </div>
        {previewError && (
          <div role="alert" style={{ fontSize: 12, color: '#ef4444' }}>{previewError}</div>
        )}
        </>)}
      </div>
      </FocusTrap>
    </div>
  )
}
