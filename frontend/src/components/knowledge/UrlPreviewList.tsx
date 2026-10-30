import { useState } from 'react'
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import { ActionButton } from '../shared/ActionButton'
import {
  getUrlPreviewPageText,
  type UrlPreview,
  type UrlPreviewPage,
  type UrlPreviewVerdict,
} from '../../api/knowledge'

const VERDICT_BADGE: Record<UrlPreviewVerdict, { label: string; tone: 'success' | 'warning' | 'danger' | 'neutral' }> = {
  good: { label: 'Good', tone: 'success' },
  low: { label: 'Low quality', tone: 'warning' },
  empty: { label: 'Empty or blocked', tone: 'danger' },
  error: { label: "Couldn't fetch", tone: 'danger' },
  duplicate: { label: 'Already added', tone: 'neutral' },
  navigation: { label: 'Navigation — not added', tone: 'neutral' },
}

export const plural = (n: number, word: string) => `${n.toLocaleString()} ${word}${n === 1 ? '' : 's'}`

interface UrlPreviewListProps {
  kbUuid: string
  preview: UrlPreview
  kept: Set<string>
  onToggle: (pageId: string) => void
  onRetry: () => void
  onCancel: () => void
  disabled?: boolean
}

/**
 * Add URLs' "Fetch & check" result (#1022): each fetched page with what adding
 * it would contribute — its text, chunk count and a verdict — so a blocked or
 * near-empty page is caught before it is indexed. Adding from here indexes
 * exactly the text shown.
 */
export function UrlPreviewList({ kbUuid, preview, kept, onToggle, onRetry, onCancel, disabled }: UrlPreviewListProps) {
  const running = preview.status === 'running'
  const pages = preview.pages
  const notAddable = pages.filter(p => !p.addable).length
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-8)', minHeight: 0 }}>
      <div style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-muted)', lineHeight: 1.5 }}>
        {running ? (
          <span role="status" aria-live="polite" style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-8)' }}>
            <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            Fetching pages… {pages.length > 0 && `${plural(pages.length, 'page')} so far`}
          </span>
        ) : null}
        {running && preview.stalled ? (
          <div
            role="alert"
            className="kb-health-summary"
            style={{ marginTop: 'var(--workspace-space-8)', marginBottom: 0, display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-12)', flexWrap: 'wrap' }}
          >
            <span style={{ flex: 1, minWidth: 200 }}>{preview.stall_message}</span>
            {!preview.workers_down && (
              <ActionButton variant="secondary" onClick={onRetry} disabled={disabled}>Retry</ActionButton>
            )}
            <ActionButton variant="secondary" onClick={onCancel} disabled={disabled}>Cancel preview</ActionButton>
          </div>
        ) : running ? null : preview.status === 'error' ? (
          <span role="alert" style={{ color: 'var(--workspace-danger)' }}>{preview.error_message || 'The preview failed.'}</span>
        ) : preview.status === 'canceled' ? (
          <span>The preview was canceled.</span>
        ) : (
          <>
            Untick anything you don&rsquo;t want. Low-quality pages start unticked.
            {notAddable > 0 && <> {plural(notAddable, 'page')} can&rsquo;t be added and {notAddable === 1 ? 'is' : 'are'} shown so you can see why.</>}
          </>
        )}
      </div>
      <ul
        aria-label="Fetched pages"
        style={{
          listStyle: 'none', margin: 0, padding: 0, overflowY: 'auto', maxHeight: 360, minHeight: 0,
          display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-8)',
        }}
      >
        {pages.map(page => (
          <PreviewRow
            key={page.page_id}
            kbUuid={kbUuid}
            previewUuid={preview.preview_uuid}
            page={page}
            kept={kept.has(page.page_id)}
            onToggle={() => onToggle(page.page_id)}
            disabled={disabled}
          />
        ))}
      </ul>
    </div>
  )
}

function PreviewRow({ kbUuid, previewUuid, page, kept, onToggle, disabled }: {
  kbUuid: string
  previewUuid: string
  page: UrlPreviewPage
  kept: boolean
  onToggle: () => void
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [fullText, setFullText] = useState<string | null>(null)
  const [loadingFull, setLoadingFull] = useState(false)
  const [fullError, setFullError] = useState<string | null>(null)
  const badge = VERDICT_BADGE[page.verdict]
  const name = page.title || page.url
  const hasMore = page.char_count > page.excerpt.length
  const meta = { fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', lineHeight: 1.4 } as const

  const loadFull = async () => {
    setLoadingFull(true)
    setFullError(null)
    try {
      const res = await getUrlPreviewPageText(kbUuid, previewUuid, page.page_id)
      setFullText(res.text)
    } catch (err) {
      setFullError(err instanceof Error ? err.message : 'Could not load the full text')
    } finally {
      setLoadingFull(false)
    }
  }

  return (
    <li style={{
      border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-medium)',
      padding: 'var(--workspace-space-8) var(--workspace-space-12)',
      backgroundColor: page.addable ? 'var(--workspace-surface)' : 'var(--workspace-hover)',
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--workspace-space-8)' }}>
        <input
          type="checkbox"
          checked={page.addable && kept}
          disabled={disabled || !page.addable}
          onChange={onToggle}
          aria-label={`Add ${name}`}
          style={{ marginTop: 3, accentColor: 'var(--workspace-accent-ink)' }}
        />
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', flexWrap: 'wrap' }}>
            <span style={{ fontSize: 'var(--workspace-font-control)', fontWeight: 600, color: 'var(--workspace-text)', overflowWrap: 'anywhere' }}>{name}</span>
            <span className="workspace-status-badge" data-tone={badge.tone}>{badge.label}</span>
          </div>
          {page.title && <div style={{ ...meta, overflowWrap: 'anywhere' }}>{page.url}</div>}
          <div style={meta}>
            {page.addable && <>{plural(page.chunk_count, 'chunk')} · </>}
            {plural(page.char_count, 'character')}
            {page.parent_url && <> · found by crawling {page.parent_url}</>}
            {page.truncated && <span style={{ color: 'var(--workspace-warning)' }}> · cut off at the length limit</span>}
          </div>
          {page.reason && (
            <div style={{ ...meta, color: page.addable ? 'var(--workspace-warning)' : 'var(--workspace-muted)' }}>{page.reason}</div>
          )}
          {page.warnings.map(w => (
            <div key={w} style={{ ...meta, color: 'var(--workspace-warning)' }}>{w}</div>
          ))}
          {page.excerpt.trim() && (
            <div>
              <ActionButton variant="quiet" onClick={() => setOpen(o => !o)} aria-expanded={open}>
                {open ? <ChevronDown size={13} aria-hidden="true" /> : <ChevronRight size={13} aria-hidden="true" />}
                {open ? 'Hide text' : 'Show text'}
              </ActionButton>
            </div>
          )}
          {open && (
            <div>
              <pre style={{
                margin: 0, maxHeight: 240, overflowY: 'auto', whiteSpace: 'pre-wrap',
                fontSize: 'var(--workspace-font-meta)', lineHeight: 1.5, color: 'var(--workspace-text)', fontFamily: 'inherit',
                backgroundColor: 'var(--workspace-canvas)', border: '1px solid var(--workspace-border)',
                borderRadius: 'var(--workspace-radius-small)', padding: 'var(--workspace-space-8)',
              }}>
                {fullText ?? page.excerpt}
              </pre>
              {hasMore && fullText === null && (
                <ActionButton variant="quiet" onClick={loadFull} disabled={loadingFull}>
                  {loadingFull ? 'Loading…' : `Show all ${plural(page.char_count, 'character')}`}
                </ActionButton>
              )}
              {fullError && <div role="alert" style={{ ...meta, color: 'var(--workspace-danger)' }}>{fullError}</div>}
            </div>
          )}
        </div>
      </div>
    </li>
  )
}
