import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { ChevronDown, ChevronRight, Loader2, X } from 'lucide-react'
import {
  commitUrlPreview,
  getUrlPreview,
  getUrlPreviewPageText,
  previewUrlsForKB,
  type UrlPreview,
  type UrlPreviewPage,
  type UrlPreviewVerdict,
} from '../../api/knowledge'

interface AddUrlsModalProps {
  kbUuid: string
  /** Called once the kept pages are queued for indexing. */
  onCommitted: (added: number) => void
  onClose: () => void
}

const POLL_MS = 2000

const VERDICT_BADGE: Record<UrlPreviewVerdict, { label: string; color: string; background: string }> = {
  good: { label: 'Good', color: '#4ade80', background: 'rgba(74,222,128,0.12)' },
  low: { label: 'Low quality', color: '#fbbf24', background: 'rgba(251,191,36,0.12)' },
  empty: { label: 'Empty or blocked', color: '#f87171', background: 'rgba(248,113,113,0.12)' },
  error: { label: "Couldn't fetch", color: '#f87171', background: 'rgba(248,113,113,0.12)' },
  duplicate: { label: 'Already added', color: '#9ca3af', background: 'rgba(156,163,175,0.12)' },
  navigation: { label: 'Navigation — not added', color: '#9ca3af', background: 'rgba(156,163,175,0.12)' },
}

const plural = (n: number, word: string) => `${n.toLocaleString()} ${word}${n === 1 ? '' : 's'}`

export function AddUrlsModal({ kbUuid, onCommitted, onClose }: AddUrlsModalProps) {
  const [text, setText] = useState('')
  const [crawlEnabled, setCrawlEnabled] = useState(false)
  const [maxCrawlPages, setMaxCrawlPages] = useState(5)
  const [allowedDomains, setAllowedDomains] = useState('')

  const [step, setStep] = useState<'enter' | 'review'>('enter')
  const [preview, setPreview] = useState<UrlPreview | null>(null)
  const [requestError, setRequestError] = useState<string | null>(null)
  // Page ids the user has kept. Pages are judged once, as they arrive: good
  // ones start kept, low-quality ones start dropped, the rest can't be kept.
  const [kept, setKept] = useState<Set<string>>(new Set())
  const judgedRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Ref, not state: a double-click's second event can fire before React
  // re-renders the disabled button, and two POSTs start two previews (or, on
  // Add, two commits) — the duplicate-source support ticket.
  const busyRef = useRef(false)
  const [busy, setBusy] = useState(false)

  const absorb = useCallback((next: UrlPreview) => {
    setPreview(next)
    setKept(prev => {
      const out = new Set(prev)
      for (const page of next.pages) {
        if (judgedRef.current.has(page.page_id)) continue
        judgedRef.current.add(page.page_id)
        if (page.verdict === 'good') out.add(page.page_id)
      }
      return out
    })
  }, [])

  // Poll while the worker is still fetching.
  const previewUuid = preview?.preview_uuid
  const running = preview?.status === 'running'
  useEffect(() => {
    if (!previewUuid || !running) return
    let cancelled = false
    const timer = window.setInterval(async () => {
      try {
        const next = await getUrlPreview(kbUuid, previewUuid)
        if (!cancelled) absorb(next)
      } catch (err) {
        if (!cancelled) setRequestError(err instanceof Error ? err.message : 'Lost track of the preview')
      }
    }, POLL_MS)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [kbUuid, previewUuid, running, absorb])

  const handlePreview = async () => {
    if (busyRef.current) return
    const urls = text.split('\n').map(u => u.trim()).filter(u => u.length > 0)
    if (urls.length === 0) return
    busyRef.current = true
    setBusy(true)
    setRequestError(null)
    try {
      const started = await previewUrlsForKB(kbUuid, urls, crawlEnabled, maxCrawlPages, allowedDomains)
      judgedRef.current = new Set()
      setKept(new Set())
      setPreview({
        preview_uuid: started.preview_uuid,
        status: 'running',
        error_message: null,
        crawl_enabled: crawlEnabled,
        pages: [],
      })
      setStep('review')
    } catch (err) {
      setRequestError(err instanceof Error ? err.message : 'Could not start the preview')
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  const keptPages = useMemo(
    () => (preview?.pages ?? []).filter(p => p.addable && kept.has(p.page_id)),
    [preview, kept],
  )
  const keptChunks = keptPages.reduce((sum, p) => sum + p.chunk_count, 0)

  const handleAdd = async () => {
    if (busyRef.current || !preview || keptPages.length === 0) return
    busyRef.current = true
    setBusy(true)
    setRequestError(null)
    try {
      await commitUrlPreview(kbUuid, preview.preview_uuid, keptPages.map(p => p.page_id))
      onCommitted(keptPages.length)
    } catch (err) {
      setRequestError(err instanceof Error ? err.message : 'Could not add the pages')
      busyRef.current = false
      setBusy(false)
    }
  }

  const toggle = (pageId: string) =>
    setKept(prev => {
      const out = new Set(prev)
      if (out.has(pageId)) out.delete(pageId)
      else out.add(pageId)
      return out
    })

  const canPreview = text.trim().length > 0 && !busy
  const canAdd = !busy && preview?.status === 'ready' && keptPages.length > 0

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
        aria-label={step === 'enter' ? 'Add URLs' : 'Review pages before adding'}
        style={{
          width: step === 'enter' ? 480 : 760, maxWidth: '100vw', maxHeight: '85vh',
          backgroundColor: '#1e1e1e', borderRadius: 12,
          border: '1px solid #3a3a3a', padding: 24,
          display: 'flex', flexDirection: 'column', gap: 16,
          overflowY: step === 'enter' ? 'auto' : 'hidden',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 16, fontWeight: 600, color: '#fff' }}>
            {step === 'enter' ? 'Add URLs' : 'Review pages before adding'}
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 4, display: 'flex' }}
          >
            <X size={18} style={{ color: '#888' }} />
          </button>
        </div>

        {step === 'enter' ? (
          <EnterStep
            text={text} setText={setText}
            crawlEnabled={crawlEnabled} setCrawlEnabled={setCrawlEnabled}
            maxCrawlPages={maxCrawlPages} setMaxCrawlPages={setMaxCrawlPages}
            allowedDomains={allowedDomains} setAllowedDomains={setAllowedDomains}
          />
        ) : preview && (
          <ReviewStep
            kbUuid={kbUuid}
            preview={preview}
            kept={kept}
            onToggle={toggle}
          />
        )}

        {requestError && (
          <div role="alert" style={{ fontSize: 13, color: '#f87171' }}>{requestError}</div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <div style={{ fontSize: 12, color: '#888' }}>
            {step === 'review' && preview?.status === 'ready' && (
              <>{plural(keptPages.length, 'page')} kept · {plural(keptChunks, 'chunk')}</>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {step === 'review' && (
              <button
                type="button"
                onClick={() => { setStep('enter'); setPreview(null); setRequestError(null) }}
                disabled={busy}
                style={secondaryButton}
              >
                Back
              </button>
            )}
            <button type="button" onClick={onClose} style={secondaryButton}>
              Cancel
            </button>
            {step === 'enter' ? (
              <button
                type="button"
                onClick={handlePreview}
                disabled={!canPreview}
                style={{ ...primaryButton, cursor: canPreview ? 'pointer' : 'default', opacity: canPreview ? 1 : 0.5 }}
              >
                {busy ? 'Starting…' : 'Preview pages'}
              </button>
            ) : (
              <button
                type="button"
                onClick={handleAdd}
                disabled={!canAdd}
                style={{ ...primaryButton, cursor: canAdd ? 'pointer' : 'default', opacity: canAdd ? 1 : 0.5 }}
              >
                {busy ? 'Adding…' : `Add ${plural(keptPages.length, 'page')}`}
              </button>
            )}
          </div>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}

const secondaryButton: React.CSSProperties = {
  padding: '8px 16px', fontSize: 13, fontWeight: 500, fontFamily: 'inherit',
  color: '#ccc', backgroundColor: 'transparent',
  border: '1px solid #3a3a3a', borderRadius: 6, cursor: 'pointer',
}

const primaryButton: React.CSSProperties = {
  padding: '8px 16px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
  color: 'var(--highlight-text-color, #000)', backgroundColor: 'var(--highlight-color, #eab308)',
  border: 'none', borderRadius: 6,
}

const fieldStyle: React.CSSProperties = {
  padding: '6px 8px', fontSize: 13, fontFamily: 'inherit',
  backgroundColor: '#2a2a2a', color: '#e5e5e5',
  border: '1px solid #3a3a3a', borderRadius: 6,
}

function EnterStep(props: {
  text: string; setText: (v: string) => void
  crawlEnabled: boolean; setCrawlEnabled: (v: boolean) => void
  maxCrawlPages: number; setMaxCrawlPages: (v: number) => void
  allowedDomains: string; setAllowedDomains: (v: string) => void
}) {
  const { text, setText, crawlEnabled, setCrawlEnabled, maxCrawlPages, setMaxCrawlPages, allowedDomains, setAllowedDomains } = props
  return (
    <>
      <div style={{ fontSize: 13, color: '#aaa' }}>
        Paste one URL per line. Each page is fetched and shown to you first — its text,
        how many chunks it would add, and how it looks — and nothing is added until you confirm.
      </div>
      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        aria-label="URLs to add, one per line"
        placeholder={'https://example.com/page1\nhttps://example.com/page2'}
        rows={8}
        style={{ ...fieldStyle, width: '100%', padding: 12, borderRadius: 8, resize: 'vertical' }}
      />

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
            The crawler will follow links on each page — including links embedded in PDFs — and the pages it finds are included in the preview.
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
              style={{ ...fieldStyle, width: 72 }}
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
              style={{ ...fieldStyle, width: '100%' }}
            />
            <div style={{ fontSize: 11, color: '#666' }}>
              Comma-separated. Include a path (e.g. example.com/irb) to limit the crawl
              to that section of the site. Defaults to the same domain as the URL.
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function ReviewStep({ kbUuid, preview, kept, onToggle }: {
  kbUuid: string
  preview: UrlPreview
  kept: Set<string>
  onToggle: (pageId: string) => void
}) {
  const running = preview.status === 'running'
  const pages = preview.pages
  const notAddable = pages.filter(p => !p.addable).length
  return (
    <>
      <div style={{ fontSize: 13, color: '#aaa', lineHeight: 1.5 }}>
        {running ? (
          <span role="status" aria-live="polite" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" />
            Fetching pages… {pages.length > 0 && `${plural(pages.length, 'page')} so far`}
          </span>
        ) : preview.status === 'error' ? (
          <span role="alert" style={{ color: '#f87171' }}>{preview.error_message || 'The preview failed.'}</span>
        ) : (
          <>
            Untick anything you don&rsquo;t want. Low-quality pages start unticked.
            {notAddable > 0 && <> {plural(notAddable, 'page')} can&rsquo;t be added and {notAddable === 1 ? 'is' : 'are'} shown so you can see why.</>}
          </>
        )}
      </div>
      <ul
        aria-label="Fetched pages"
        style={{ listStyle: 'none', margin: 0, padding: 0, overflowY: 'auto', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 8 }}
      >
        {pages.map(page => (
          <PreviewRow
            key={page.page_id}
            kbUuid={kbUuid}
            previewUuid={preview.preview_uuid}
            page={page}
            kept={kept.has(page.page_id)}
            onToggle={() => onToggle(page.page_id)}
          />
        ))}
      </ul>
    </>
  )
}

function PreviewRow({ kbUuid, previewUuid, page, kept, onToggle }: {
  kbUuid: string
  previewUuid: string
  page: UrlPreviewPage
  kept: boolean
  onToggle: () => void
}) {
  const [open, setOpen] = useState(false)
  const [fullText, setFullText] = useState<string | null>(null)
  const [loadingFull, setLoadingFull] = useState(false)
  const badge = VERDICT_BADGE[page.verdict]
  const name = page.title || page.url
  const hasMore = page.char_count > page.excerpt.length

  const loadFull = async () => {
    setLoadingFull(true)
    try {
      const res = await getUrlPreviewPageText(kbUuid, previewUuid, page.page_id)
      setFullText(res.text)
    } finally {
      setLoadingFull(false)
    }
  }

  return (
    <li style={{
      border: '1px solid #3a3a3a', borderRadius: 8, padding: '10px 12px',
      backgroundColor: page.addable ? '#242424' : '#202020',
      opacity: page.addable ? 1 : 0.75,
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <input
          type="checkbox"
          checked={page.addable && kept}
          disabled={!page.addable}
          onChange={onToggle}
          aria-label={`Add ${name}`}
          style={{ marginTop: 3, accentColor: 'var(--highlight-color, #eab308)' }}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: '#e5e5e5', overflowWrap: 'anywhere' }}>{name}</span>
            <span style={{
              fontSize: 11, fontWeight: 600, padding: '1px 8px', borderRadius: 999,
              color: badge.color, backgroundColor: badge.background, whiteSpace: 'nowrap',
            }}>
              {badge.label}
            </span>
          </div>
          {page.title && (
            <div style={{ fontSize: 11, color: '#777', overflowWrap: 'anywhere' }}>{page.url}</div>
          )}
          <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>
            {page.addable && <>{plural(page.chunk_count, 'chunk')} · </>}
            {plural(page.char_count, 'character')}
            {page.parent_url && <> · found by crawling {page.parent_url}</>}
            {page.truncated && <span style={{ color: '#fbbf24' }}> · cut off at the length limit</span>}
          </div>
          {page.reason && (
            <div style={{ fontSize: 12, color: page.addable ? '#fbbf24' : '#aaa', marginTop: 4 }}>{page.reason}</div>
          )}
          {page.warnings.map(w => (
            <div key={w} style={{ fontSize: 12, color: '#fbbf24', marginTop: 4 }}>{w}</div>
          ))}
          {page.excerpt.trim() && (
            <button
              type="button"
              onClick={() => setOpen(o => !o)}
              aria-expanded={open}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 4, marginTop: 6, padding: 0,
                fontSize: 12, fontFamily: 'inherit', color: '#aaa',
                background: 'transparent', border: 'none', cursor: 'pointer',
              }}
            >
              {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              {open ? 'Hide text' : 'Show text'}
            </button>
          )}
          {open && (
            <div style={{ marginTop: 6 }}>
              <pre style={{
                margin: 0, maxHeight: 240, overflowY: 'auto', whiteSpace: 'pre-wrap',
                fontSize: 12, lineHeight: 1.5, color: '#ccc', fontFamily: 'inherit',
                backgroundColor: '#1a1a1a', border: '1px solid #333', borderRadius: 6, padding: 10,
              }}>
                {fullText ?? page.excerpt}
              </pre>
              {hasMore && fullText === null && (
                <button
                  type="button"
                  onClick={loadFull}
                  disabled={loadingFull}
                  style={{
                    marginTop: 4, padding: 0, fontSize: 12, fontFamily: 'inherit',
                    color: 'var(--highlight-color, #eab308)', background: 'transparent',
                    border: 'none', cursor: loadingFull ? 'default' : 'pointer',
                  }}
                >
                  {loadingFull ? 'Loading…' : `Show all ${plural(page.char_count, 'character')}`}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </li>
  )
}
