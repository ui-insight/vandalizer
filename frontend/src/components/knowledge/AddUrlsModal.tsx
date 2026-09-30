import { usePanelEffect } from '../shared/usePanelEffect'
import { useRef, useState } from 'react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { X } from 'lucide-react'

interface AddUrlsModalProps {
  onSubmit: (urls: string[], crawlEnabled: boolean, maxCrawlPages: number, allowedDomains: string) => void | Promise<void>
  onClose: () => void
}

export function AddUrlsModal({ onSubmit, onClose }: AddUrlsModalProps) {
  const [text, setText] = useState('')
  const [crawlEnabled, setCrawlEnabled] = useState(false)
  const [maxCrawlPages, setMaxCrawlPages] = useState(5)
  const [allowedDomains, setAllowedDomains] = useState('')
  const [error, setError] = useState<string | null>(null)

  usePanelEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !submittedRef.current) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Ref, not state: a double-click's second event can fire before React
  // re-renders the disabled button, and two POSTs enqueue two ingest runs
  // that race each other (the duplicate-source support ticket).
  const submittedRef = useRef(false)
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = async () => {
    if (submittedRef.current) return
    const rows = text.split('\n').map((value, index) => ({ value: value.trim(), line: index + 1 })).filter(row => row.value)
    const urls = rows.map(row => row.value.includes('://') ? row.value : `https://${row.value}`)
    if (urls.length > 0) {
      const invalid = urls.findIndex(value => { try { const url = new URL(value); return !['http:', 'https:'].includes(url.protocol) } catch { return true } })
      if (invalid !== -1) { setError(`Line ${rows[invalid].line} needs a valid http:// or https:// URL.`); return }
      submittedRef.current = true
      setSubmitted(true)
      setError(null)
      try {
        await onSubmit([...new Set(urls)], crawlEnabled, maxCrawlPages, allowedDomains)
        onClose()
      } catch (e) {
        setError(`${e instanceof Error ? e.message : 'Could not add URLs'}. Your URLs and settings are preserved; retry Add URLs.`)
      } finally { submittedRef.current = false; setSubmitted(false) }
    }
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        backgroundColor: 'rgba(0,0,0,0.6)',
      }}
      onClick={() => { if (!submitted) onClose() }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Add URLs"
        style={{
          width: 480, maxWidth: 'calc(100vw - 24px)', maxHeight: '90dvh',
          backgroundColor: '#1e1e1e', borderRadius: 12,
          border: '1px solid #3a3a3a', padding: 16,
          display: 'flex', flexDirection: 'column', gap: 16,
          overflow: 'hidden',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
          <span style={{ fontSize: 16, fontWeight: 600, color: '#fff' }}>Add URLs</span>
          <button
            onClick={onClose}
            aria-label="Close"
            disabled={submitted}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 4, display: 'flex' }}
          >
            <X size={18} style={{ color: '#888' }} />
          </button>
        </div>
        <div style={{ overflowY: 'auto', minHeight: 0, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ fontSize: 13, color: '#aaa' }}>
          Paste one website URL per line; addresses without a scheme use https://. Adding queues retrieval; each source becomes usable after its text is indexed. Existing URLs are skipped; use Refresh on their source rows to fetch them again.
        </div>
        <textarea
          value={text}
          disabled={submitted}
          onChange={e => setText(e.target.value)}
          aria-label="URLs to add, one per line"
          placeholder={'https://example.com/page1\nhttps://example.com/page2'}
          rows={8}
          style={{
            width: '100%', padding: 12, fontSize: 13, fontFamily: 'inherit',
            backgroundColor: '#2a2a2a', color: '#e5e5e5',
            border: '1px solid #3a3a3a', borderRadius: 8,
            resize: 'vertical', minHeight: 120, flexShrink: 0,
          }}
        />

        {/* Crawl toggle */}
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
          <input
            type="checkbox"
            disabled={submitted}
            checked={crawlEnabled}
            onChange={e => setCrawlEnabled(e.target.checked)}
            style={{ accentColor: 'var(--highlight-color, #eab308)' }}
          />
          <span style={{ fontSize: 13, color: '#e5e5e5' }}>Enable crawling</span>
        </label>

        {crawlEnabled && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingLeft: 4 }}>
            <div style={{ fontSize: 12, color: '#888', lineHeight: 1.5 }}>
              The crawler will follow links on each page — including links embedded in PDFs — and add discovered pages as additional sources.
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <label htmlFor="add-urls-max-pages" style={{ fontSize: 13, color: '#aaa', minWidth: 80 }}>Max pages</label>
              <input
                id="add-urls-max-pages"
                type="number"
                disabled={submitted}
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
                disabled={submitted}
                value={allowedDomains}
                onChange={e => setAllowedDomains(e.target.value)}
                placeholder="example.com, example.com/section"
                style={{
                  width: '100%', padding: '6px 8px', fontSize: 13, fontFamily: 'inherit',
                  backgroundColor: '#2a2a2a', color: '#e5e5e5',
                  border: '1px solid #3a3a3a', borderRadius: 6,
                }}
              />
              <div style={{ fontSize: 12, color: '#b8bec7' }}>
                Comma-separated. Include a path (e.g. example.com/irb) to limit the crawl
                to that section of the site. Defaults to the same domain as the URL.
              </div>
            </div>
          </div>
        )}

        </div>
        {error && <div role="alert" style={{ fontSize: 13, color: '#fca5a5', lineHeight: 1.6, overflowWrap: 'anywhere' }}>{error}</div>}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, flexShrink: 0 }}>
          <button
            onClick={onClose}
            disabled={submitted}
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
            {submitted ? 'Adding…' : 'Add URLs'}
          </button>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
