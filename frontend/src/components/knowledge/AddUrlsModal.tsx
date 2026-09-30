import { FieldLabel, FieldMessage } from '../shared/FormField'
import { ActionButton } from '../shared/ActionButton'
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
  const [urlError, setUrlError] = useState<string | null>(null)
  const urlsRef = useRef<HTMLTextAreaElement>(null)

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
      if (invalid !== -1) { setUrlError(`Line ${rows[invalid].line} needs a valid http:// or https:// URL.`); urlsRef.current?.focus(); return }
      setUrlError(null)
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
          backgroundColor: 'var(--workspace-canvas)', borderRadius: 'var(--workspace-radius-large)',
          border: '1px solid var(--workspace-border)', padding: 'var(--workspace-space-16)',
          display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-16)',
          overflow: 'hidden',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
          <span style={{ fontSize: 'var(--workspace-font-card-title)', fontWeight: 600, color: 'var(--workspace-text)' }}>Add URLs</span>
          <ActionButton variant="quiet" iconOnly
            onClick={onClose}
            aria-label="Close"
            disabled={submitted}

          >
            <X size={18} style={{ color: 'var(--workspace-muted)' }} />
          </ActionButton>
        </div>
        <div style={{ overflowY: 'auto', minHeight: 0, display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-16)' }}>
        <div id="add-urls-help" style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-muted)' }}>
          Paste one website URL per line; addresses without a scheme use https://. Adding queues retrieval; each source becomes usable after its text is indexed. Existing URLs are skipped; use Refresh on their source rows to fetch them again.
        </div>
        <FieldLabel htmlFor="add-urls-input" required>URLs to add, one per line</FieldLabel>
        <textarea
          id="add-urls-input"
          ref={urlsRef}
          aria-required="true"
          aria-invalid={!!urlError}
          aria-describedby={`add-urls-help${urlError ? ' add-urls-field-error' : ''}`}
          value={text}
          disabled={submitted}
          onChange={e => { setText(e.target.value); setUrlError(null) }}
          aria-label="URLs to add, one per line"
          placeholder={'https://example.com/page1\nhttps://example.com/page2'}
          rows={8}
          style={{
            width: '100%', padding: 'var(--workspace-space-12)', fontSize: 'var(--workspace-font-control)', fontFamily: 'inherit',
            backgroundColor: 'var(--workspace-surface)', color: 'var(--workspace-text)',
            border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-medium)',
            resize: 'vertical', minHeight: 120, flexShrink: 0,
          }}
        />

        {urlError && <FieldMessage id="add-urls-field-error" error>{urlError}</FieldMessage>}

        {/* Crawl toggle */}
        <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', cursor: 'pointer' }}>
          <input
            type="checkbox"
            disabled={submitted}
            checked={crawlEnabled}
            onChange={e => setCrawlEnabled(e.target.checked)}
            style={{ accentColor: 'var(--workspace-accent-ink)' }}
          />
          <span style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)' }}>Enable crawling</span>
        </label>

        {crawlEnabled && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-12)', paddingLeft: 'var(--workspace-space-4)' }}>
            <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', lineHeight: 1.5 }}>
              The crawler will follow links on each page — including links embedded in PDFs — and add discovered pages as additional sources.
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)' }}>
              <FieldLabel htmlFor="add-urls-max-pages" required>Max pages</FieldLabel>
              <input
                id="add-urls-max-pages"
                aria-required="true"
                type="number"
                disabled={submitted}
                value={maxCrawlPages}
                onChange={e => setMaxCrawlPages(Math.max(1, Math.min(50, parseInt(e.target.value) || 1)))}
                min={1}
                max={50}
                style={{
                  width: 72, padding: "var(--workspace-space-6) var(--workspace-space-8)", fontSize: 'var(--workspace-font-control)', fontFamily: 'inherit',
                  backgroundColor: 'var(--workspace-surface)', color: 'var(--workspace-text)',
                  border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-small)',
                }}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-4)' }}>
              <FieldLabel htmlFor="add-urls-allowed-domains" optional>Allowed domains</FieldLabel>
              <input
                id="add-urls-allowed-domains"
                type="text"
                disabled={submitted}
                value={allowedDomains}
                onChange={e => setAllowedDomains(e.target.value)}
                placeholder="example.com, example.com/section"
                style={{
                  width: '100%', padding: "var(--workspace-space-6) var(--workspace-space-8)", fontSize: 'var(--workspace-font-control)', fontFamily: 'inherit',
                  backgroundColor: 'var(--workspace-surface)', color: 'var(--workspace-text)',
                  border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-small)',
                }}
              />
              <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
                Comma-separated. Include a path (e.g. example.com/irb) to limit the crawl
                to that section of the site. Defaults to the same domain as the URL.
              </div>
            </div>
          </div>
        )}

        </div>
        {error && <FieldMessage id="add-urls-submit-error" error>{error}</FieldMessage>}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--workspace-space-8)', flexShrink: 0 }}>
          <ActionButton variant="secondary"
            onClick={onClose}
            disabled={submitted}

          >
            Cancel
          </ActionButton>
          <ActionButton variant="primary" aria-busy={submitted}
            onClick={handleSubmit}
            disabled={!text.trim() || submitted}

          >
            {submitted ? 'Adding…' : 'Add URLs'}
          </ActionButton>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
