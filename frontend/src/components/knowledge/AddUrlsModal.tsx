import { FieldLabel, FieldMessage } from '../shared/FormField'
import { ActionButton } from '../shared/ActionButton'
import { usePanelEffect } from '../shared/usePanelEffect'
import { useEffect, useRef, useState } from 'react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { ArrowLeft, Loader2, X } from 'lucide-react'
import { TopicSourceFinder } from './TopicSourceFinder'
import { UrlReviewList, type UrlCandidate } from './UrlReviewList'
import { extractUrls } from '../../utils/extractUrls'
import { getSourceSuggestionsAvailable, readSitemap } from '../../api/knowledge'

// Mirrors MAX_URLS_PER_ADD / MAX_CRAWL_URLS_PER_ADD in routers/knowledge.py.
const MAX_URLS_PER_ADD = 500
const MAX_CRAWL_URLS_PER_ADD = 25
// A list of links is small; a file this size is a document, not a list.
const MAX_FILE_BYTES = 5 * 1024 * 1024

type Method = 'paste' | 'file' | 'sitemap' | 'topic'

const METHOD_LABELS: Record<Method, string> = {
  paste: 'Paste',
  file: 'File',
  sitemap: 'Sitemap',
  topic: 'Topic',
}

interface AddUrlsModalProps {
  /** Enables the Sitemap and Topic ways in (both read on the server for this KB). */
  kbUuid?: string
  onSubmit: (urls: string[], crawlEnabled: boolean, maxCrawlPages: number, allowedDomains: string) => void | Promise<void>
  onClose: () => void
}

/**
 * Add URLs, in two steps: gather links, then review them (feature request —
 * links could only be typed one per line). Links come from pasted text of any
 * kind (an email, a document: the links are pulled out of it), a file, a
 * site's sitemap, or a topic search. The review step lists every one found;
 * only the checked ones are added.
 */
export function AddUrlsModal({ kbUuid, onSubmit, onClose }: AddUrlsModalProps) {
  const [step, setStep] = useState<'choose' | 'review'>('choose')
  const [method, setMethod] = useState<Method>('paste')
  const [topicAvailable, setTopicAvailable] = useState(false)

  const [text, setText] = useState('')
  const [fileName, setFileName] = useState<string | null>(null)
  const [fileUrls, setFileUrls] = useState<string[]>([])
  const [fileError, setFileError] = useState<string | null>(null)
  const [sitemapUrl, setSitemapUrl] = useState('')
  const [readingSitemap, setReadingSitemap] = useState(false)
  const [sitemapError, setSitemapError] = useState<string | null>(null)
  const [sourceNote, setSourceNote] = useState<string | null>(null)

  const [candidates, setCandidates] = useState<UrlCandidate[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const [crawlEnabled, setCrawlEnabled] = useState(false)
  const [maxCrawlPages, setMaxCrawlPages] = useState(5)
  const [allowedDomains, setAllowedDomains] = useState('')
  const [error, setError] = useState<string | null>(null)
  const pasteRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!kbUuid) return
    let cancelled = false
    getSourceSuggestionsAvailable(kbUuid)
      .then(r => { if (!cancelled) setTopicAvailable(r.available) })
      .catch(() => { if (!cancelled) setTopicAvailable(false) })
    return () => { cancelled = true }
  }, [kbUuid])

  const methods: Method[] = ['paste', 'file', ...(kbUuid ? ['sitemap' as const] : []), ...(topicAvailable ? ['topic' as const] : [])]

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

  const pastedUrls = method === 'paste' ? extractUrls(text) : []

  // Links a person gathered themselves start checked; a sitemap or a search
  // offers pages to choose from, so those start unchecked.
  const review = (found: UrlCandidate[], preselect: boolean, note: string | null = null) => {
    setCandidates(found)
    setSelected(preselect ? new Set(found.filter(c => !c.inKb).map(c => c.url)) : new Set())
    setSourceNote(note)
    setError(null)
    setStep('review')
  }

  const readFile = async (file: File | undefined) => {
    setFileError(null)
    setFileUrls([])
    setFileName(file?.name ?? null)
    if (!file) return
    if (file.size > MAX_FILE_BYTES) {
      setFileError(`${file.name} is larger than 5 MB. Upload a list of links, not the documents themselves.`)
      return
    }
    try {
      const urls = extractUrls(await file.text())
      setFileUrls(urls)
      if (urls.length === 0) setFileError(`No web links found in ${file.name}.`)
    } catch {
      setFileError(`${file.name} could not be read as text.`)
    }
  }

  const loadSitemap = async () => {
    if (!kbUuid || !sitemapUrl.trim() || readingSitemap) return
    setReadingSitemap(true)
    setSitemapError(null)
    try {
      const result = await readSitemap(kbUuid, sitemapUrl.trim())
      if (result.pages.length === 0) {
        setSitemapError(`${result.sitemap_url} lists no pages.`)
        return
      }
      const notes = [`From ${result.sitemap_url}.`]
      if (result.truncated) notes.push(`The sitemap lists more pages than can be shown; the first ${result.pages.length} are here.`)
      if (result.errors.length) notes.push(`${result.errors.length} of its sitemaps could not be read.`)
      review(
        result.pages.map(p => ({ url: p.url, inKb: p.in_kb, detail: p.lastmod ? `Updated ${p.lastmod.slice(0, 10)}` : null })),
        false,
        notes.join(' '),
      )
    } catch (e) {
      setSitemapError(e instanceof Error ? e.message : 'Could not read the sitemap')
    } finally {
      setReadingSitemap(false)
    }
  }

  const limit = crawlEnabled ? MAX_CRAWL_URLS_PER_ADD : MAX_URLS_PER_ADD
  const overLimit = selected.size > limit

  const handleSubmit = async () => {
    if (submittedRef.current || selected.size === 0 || overLimit) return
    submittedRef.current = true
    setSubmitted(true)
    setError(null)
    try {
      // Kept in the order they were found, not the order they were checked.
      await onSubmit(candidates.filter(c => selected.has(c.url)).map(c => c.url), crawlEnabled, maxCrawlPages, allowedDomains)
      onClose()
    } catch (e) {
      setError(`${e instanceof Error ? e.message : 'Could not add URLs'}. Your selection and settings are preserved; retry Add.`)
    } finally { submittedRef.current = false; setSubmitted(false) }
  }

  const chooseNext = () => {
    if (method === 'paste') {
      if (pastedUrls.length === 0) { pasteRef.current?.focus(); return }
      review(pastedUrls.map(url => ({ url })), true)
    } else if (method === 'file') {
      if (fileUrls.length) review(fileUrls.map(url => ({ url })), true, fileName ? `From ${fileName}.` : null)
    } else if (method === 'sitemap') {
      void loadSitemap()
    }
  }

  const inputStyle = {
    width: '100%', padding: 'var(--workspace-space-6) var(--workspace-space-8)', fontSize: 'var(--workspace-font-control)', fontFamily: 'inherit',
    backgroundColor: 'var(--workspace-surface)', color: 'var(--workspace-text)',
    border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-small)',
  } as const

  const nextDisabled = submitted || (
    method === 'paste' ? pastedUrls.length === 0
      : method === 'file' ? fileUrls.length === 0
        : method === 'sitemap' ? !sitemapUrl.trim() || readingSitemap
          : true
  )

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
          width: 560, maxWidth: 'calc(100vw - 24px)', maxHeight: '90dvh',
          backgroundColor: 'var(--workspace-canvas)', borderRadius: 'var(--workspace-radius-large)',
          border: '1px solid var(--workspace-border)', padding: 'var(--workspace-space-16)',
          display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-16)',
          overflow: 'hidden',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
          <span style={{ fontSize: 'var(--workspace-font-card-title)', fontWeight: 600, color: 'var(--workspace-text)' }}>
            {step === 'choose' ? 'Add URLs' : 'Review links'}
          </span>
          <ActionButton variant="quiet" iconOnly onClick={onClose} aria-label="Close" disabled={submitted}>
            <X size={18} style={{ color: 'var(--workspace-muted)' }} />
          </ActionButton>
        </div>

        <div style={{ overflowY: 'auto', minHeight: 0, display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-16)' }}>
        {step === 'choose' && (
          <>
            <div role="tablist" aria-label="Where the links come from" style={{ display: 'flex', gap: 'var(--workspace-space-4)', borderBottom: '1px solid var(--workspace-border)', flexShrink: 0 }}>
              {methods.map(m => (
                <button
                  key={m}
                  type="button"
                  role="tab"
                  id={`add-urls-tab-${m}`}
                  aria-selected={method === m}
                  aria-controls="add-urls-method-panel"
                  onClick={() => setMethod(m)}
                  style={{
                    padding: 'var(--workspace-space-6) var(--workspace-space-12)', background: 'transparent', cursor: 'pointer',
                    border: 'none', borderBottom: `2px solid ${method === m ? 'var(--workspace-accent-ink)' : 'transparent'}`,
                    color: method === m ? 'var(--workspace-text)' : 'var(--workspace-muted)',
                    fontSize: 'var(--workspace-font-control)', fontWeight: method === m ? 600 : 400, fontFamily: 'inherit',
                  }}
                >
                  {METHOD_LABELS[m]}
                </button>
              ))}
            </div>

            <div id="add-urls-method-panel" role="tabpanel" aria-labelledby={`add-urls-tab-${method}`} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-8)' }}>
              {method === 'paste' && (
                <>
                  <FieldLabel htmlFor="add-urls-input" required>Links, or any text with links in it</FieldLabel>
                  <textarea
                    id="add-urls-input"
                    ref={pasteRef}
                    aria-describedby="add-urls-help"
                    value={text}
                    disabled={submitted}
                    onChange={e => setText(e.target.value)}
                    placeholder={'https://example.com/page1\nhttps://example.com/page2\n\nor paste an email or document; its links are picked out'}
                    rows={8}
                    style={{ ...inputStyle, padding: 'var(--workspace-space-12)', borderRadius: 'var(--workspace-radius-medium)', resize: 'vertical', minHeight: 120 }}
                  />
                  <div id="add-urls-help" role="status" style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
                    {text.trim()
                      ? `${pastedUrls.length} link${pastedUrls.length === 1 ? '' : 's'} found.`
                      : 'One per line, or paste an email or document. Addresses without http:// use https://.'}
                  </div>
                </>
              )}

              {method === 'file' && (
                <>
                  <FieldLabel htmlFor="add-urls-file" required>File of links</FieldLabel>
                  <input
                    id="add-urls-file"
                    type="file"
                    accept=".txt,.csv,.tsv,.md,.html,.htm,.xml,.json,text/plain,text/csv,text/html"
                    disabled={submitted}
                    onChange={e => { void readFile(e.target.files?.[0]) }}
                    style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)' }}
                  />
                  <div role="status" style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
                    {fileUrls.length
                      ? `${fileUrls.length} link${fileUrls.length === 1 ? '' : 's'} found in ${fileName}.`
                      : 'A text, CSV, Markdown or HTML file, such as a bookmarks export. Every web link in it is picked out.'}
                  </div>
                  {fileError && <FieldMessage id="add-urls-file-error" error>{fileError}</FieldMessage>}
                </>
              )}

              {method === 'sitemap' && (
                <>
                  <FieldLabel htmlFor="add-urls-sitemap" required>Sitemap or site address</FieldLabel>
                  <input
                    id="add-urls-sitemap"
                    type="text"
                    value={sitemapUrl}
                    disabled={submitted || readingSitemap}
                    onChange={e => { setSitemapUrl(e.target.value); setSitemapError(null) }}
                    onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); void loadSitemap() } }}
                    placeholder="https://www.example.edu/sitemap.xml or www.example.edu"
                    style={inputStyle}
                  />
                  <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', lineHeight: 1.5 }}>
                    A sitemap is the site's own list of its pages. Pick exactly the ones to add, rather than crawling and getting whatever the links lead to. Given a site address, its sitemap is looked up.
                  </div>
                  {sitemapError && <FieldMessage id="add-urls-sitemap-error" error>{sitemapError}</FieldMessage>}
                </>
              )}

              {method === 'topic' && kbUuid && (
                <TopicSourceFinder
                  kbUuid={kbUuid}
                  disabled={submitted}
                  onResults={(suggestions, alreadyInKb) => review(
                    suggestions.map(s => ({ url: s.url, title: s.title, detail: s.reason || s.snippet || null })),
                    false,
                    alreadyInKb ? `${alreadyInKb} more page${alreadyInKb === 1 ? '' : 's'} found ${alreadyInKb === 1 ? 'is' : 'are'} already in this knowledge base.` : null,
                  )}
                />
              )}
            </div>
          </>
        )}

        {step === 'review' && (
          <>
            {sourceNote && <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>{sourceNote}</div>}
            <UrlReviewList candidates={candidates} selected={selected} onChange={setSelected} disabled={submitted} />

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
                    style={{ ...inputStyle, width: 72 }}
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
                    style={inputStyle}
                  />
                  <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
                    Comma-separated. Include a path (e.g. example.com/irb) to limit the crawl
                    to that section of the site. Defaults to the same domain as the URL.
                  </div>
                </div>
              </div>
            )}

            {overLimit && (
              <FieldMessage id="add-urls-limit" error>
                {`At most ${limit} links can be added at once${crawlEnabled ? ' with crawling on' : ''}; ${selected.size} are selected. Add them in parts.`}
              </FieldMessage>
            )}
            <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
              Each page is fetched and becomes usable once its text is indexed. Links already in this knowledge base are skipped; use Refresh on their source rows to fetch them again.
            </div>
          </>
        )}
        </div>

        {error && <FieldMessage id="add-urls-submit-error" error>{error}</FieldMessage>}
        <div style={{ display: 'flex', justifyContent: step === 'review' ? 'space-between' : 'flex-end', gap: 'var(--workspace-space-8)', flexShrink: 0 }}>
          {step === 'review' && (
            <ActionButton variant="quiet" onClick={() => { setStep('choose'); setError(null) }} disabled={submitted}>
              <ArrowLeft size={14} aria-hidden="true" /> Back
            </ActionButton>
          )}
          <div style={{ display: 'flex', gap: 'var(--workspace-space-8)' }}>
            <ActionButton variant="secondary" onClick={onClose} disabled={submitted}>Cancel</ActionButton>
            {step === 'choose' && method !== 'topic' && (
              <ActionButton variant="primary" onClick={chooseNext} disabled={nextDisabled} aria-busy={readingSitemap}>
                {readingSitemap ? <><Loader2 size={14} className="animate-spin" aria-hidden="true" /> Reading sitemap…</> : method === 'sitemap' ? 'Read sitemap' : 'Review links'}
              </ActionButton>
            )}
            {step === 'review' && (
              <ActionButton variant="primary" aria-busy={submitted} onClick={handleSubmit} disabled={selected.size === 0 || overLimit || submitted}>
                {submitted ? 'Adding…' : `Add ${selected.size} URL${selected.size === 1 ? '' : 's'}`}
              </ActionButton>
            )}
          </div>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
