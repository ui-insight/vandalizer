import { useEffect, useState } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { X, FileText, Globe, ExternalLink, Loader2, AlertCircle, Check } from 'lucide-react'
import { getKBSource, setKBSourceReference } from '../../api/knowledge'
import type { KnowledgeBaseSource, KnowledgeBaseSourceDetail } from '../../types/knowledge'
import { DocumentViewer } from '../files/DocumentViewer'

interface Props {
  kbUuid: string
  source: KnowledgeBaseSource  // initial summary from the list — used for instant header
  onClose: () => void
  onUpdated?: () => void  // called after the source's provenance is edited, so the list refreshes
}

export function KBSourceInspectorModal({ kbUuid, source, onClose, onUpdated }: Props) {
  const [detail, setDetail] = useState<KnowledgeBaseSourceDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Editable provenance ("Source: …"). For url sources the origin URL is the
  // default when nothing was entered yet; the user can override either type.
  const [sourceDraft, setSourceDraft] = useState('')
  const [savingSource, setSavingSource] = useState(false)
  // For document sources, default to the extracted text the KB actually
  // indexed (what "view the source" should mean), with a toggle to the
  // original file.
  const [docView, setDocView] = useState<'text' | 'file'>('text')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getKBSource(kbUuid, source.uuid)
      .then(d => {
        if (cancelled) return
        setDetail(d)
        setSourceDraft(d.source_reference || (d.source_type === 'url' ? (d.url || '') : ''))
      })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load source') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [kbUuid, source.uuid])

  // Close on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const savedSource = detail?.source_reference || (detail?.source_type === 'url' ? (detail?.url || '') : '')
  const sourceDirty = sourceDraft.trim() !== (savedSource || '').trim()

  const saveSource = async () => {
    if (savingSource || !sourceDirty) return
    setSavingSource(true)
    try {
      const updated = await setKBSourceReference(kbUuid, source.uuid, sourceDraft.trim())
      setDetail(prev => (prev ? { ...prev, source_reference: updated.source_reference } : prev))
      onUpdated?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save source')
    } finally {
      setSavingSource(false)
    }
  }

  const isDoc = source.source_type === 'document'
  const displayTitle =
    source.document_title
    || source.url_title
    || source.url
    || source.document_uuid
    || 'Source'

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.65)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1100, padding: 24,
      }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Source: ${displayTitle}`}
        onClick={e => e.stopPropagation()}
        style={{
          width: '90vw', maxWidth: 960, height: '85vh',
          display: 'flex', flexDirection: 'column',
          backgroundColor: '#1f1f1f',
          border: '1px solid #2e2e2e', borderRadius: 10,
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '14px 18px',
          borderBottom: '1px solid #2e2e2e',
          flexShrink: 0,
        }}>
          {isDoc
            ? <FileText size={18} style={{ color: '#a78bfa', flexShrink: 0 }} aria-hidden="true" />
            : <Globe size={18} style={{ color: '#60a5fa', flexShrink: 0 }} aria-hidden="true" />}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: 14, fontWeight: 600, color: '#fff',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {displayTitle}
            </div>
            <div style={{ fontSize: 11, color: '#888', marginTop: 2 }}>
              {isDoc ? 'Document source' : 'URL source'}
              {source.chunk_count > 0 && <> · {source.chunk_count} chunks</>}
              {source.status !== 'ready' && <> · {source.status}</>}
            </div>
          </div>
          {isDoc && source.document_uuid && (
            <div style={{ display: 'inline-flex', border: '1px solid #2e2e2e', borderRadius: 5, overflow: 'hidden' }}>
              {(['text', 'file'] as const).map(mode => (
                <button
                  key={mode}
                  type="button"
                  aria-pressed={docView === mode}
                  onClick={() => setDocView(mode)}
                  style={{
                    fontSize: 12, padding: '4px 10px', fontFamily: 'inherit', cursor: 'pointer',
                    border: 'none',
                    backgroundColor: docView === mode ? '#2e2e2e' : 'transparent',
                    color: docView === mode ? '#fff' : '#9ca3af',
                  }}
                >
                  {mode === 'text' ? 'Text' : 'File'}
                </button>
              ))}
            </div>
          )}
          {!isDoc && source.url && (
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              title="Open URL in new tab"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                fontSize: 12, color: '#60a5fa', textDecoration: 'none',
                padding: '4px 8px', border: '1px solid #2e2e2e', borderRadius: 5,
              }}
            >
              <ExternalLink size={12} />
              Open
            </a>
          )}
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 4, color: '#888' }}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        {/* Verifiable provenance — editable, shown for both URL and document sources.
            Lets a user confirm/record where the content came from (origin URL or citation). */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '8px 18px', borderBottom: '1px solid #2e2e2e', flexShrink: 0,
        }}>
          <span id="kb-source-ref-label" style={{ fontSize: 11, color: '#888', flexShrink: 0 }}>Source</span>
          <input
            aria-labelledby="kb-source-ref-label"
            value={sourceDraft}
            onChange={e => setSourceDraft(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); saveSource() } }}
            placeholder={isDoc ? 'e.g. APM Ch.45 — uidaho.edu/apm/45' : 'Origin URL'}
            maxLength={2000}
            disabled={savingSource}
            style={{
              flex: 1, fontSize: 12, color: '#e5e5e5',
              backgroundColor: '#161616', border: '1px solid #2e2e2e',
              borderRadius: 5, padding: '5px 8px', fontFamily: 'inherit',
            }}
          />
          {sourceDirty && (
            <button
              type="button"
              aria-label="Save source"
              onClick={saveSource}
              disabled={savingSource}
              title="Save source"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                fontSize: 12, color: '#fff', backgroundColor: '#2563eb',
                border: 'none', borderRadius: 5, padding: '5px 10px',
                cursor: savingSource ? 'default' : 'pointer', flexShrink: 0,
              }}
            >
              {savingSource
                ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" />
                : <Check size={12} aria-hidden="true" />}
              Save
            </button>
          )}
        </div>

        {/* Body */}
        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex' }}>
          {isDoc && docView === 'file' ? (
            source.document_uuid ? (
              <div style={{ flex: 1, minWidth: 0, minHeight: 0 }}>
                <DocumentViewer docUuid={source.document_uuid} />
              </div>
            ) : (
              <EmptyState message="No document associated with this source." />
            )
          ) : (
            <SourceContentInspector
              loading={loading}
              error={error}
              detail={detail}
              fallbackUrl={source.url}
              isDoc={isDoc}
            />
          )}
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div style={{
      flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 13, color: '#888',
    }}>
      {message}
    </div>
  )
}

function SourceContentInspector({
  loading, error, detail, fallbackUrl, isDoc = false,
}: {
  loading: boolean
  error: string | null
  detail: KnowledgeBaseSourceDetail | null
  fallbackUrl?: string
  isDoc?: boolean
}) {
  if (loading) {
    return (
      <div role="status" aria-live="polite" style={{
        flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: '#888',
      }}>
        <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" />
        <span style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>Loading source…</span>
      </div>
    )
  }
  if (error) {
    return (
      <div role="alert" style={{
        flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
        gap: 8, color: '#ef4444', fontSize: 13,
      }}>
        <AlertCircle size={16} aria-hidden="true" />
        {error}
      </div>
    )
  }
  if (!detail) return null

  const childCount = detail.child_sources?.length || 0
  const hasContent = !!(detail.content && detail.content.trim())

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      padding: '14px 18px', overflowY: 'auto',
    }}>
      {/* Meta block */}
      <div style={{
        display: 'grid', gridTemplateColumns: '120px 1fr', gap: '4px 12px',
        fontSize: 12, color: '#cbd5e1', marginBottom: 16,
      }}>
        {!isDoc && (
          <>
            <div style={{ color: '#888' }}>URL</div>
            <div style={{ wordBreak: 'break-all' }}>
              {detail.url ? (
                <a
                  href={detail.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: '#60a5fa', textDecoration: 'none' }}
                >
                  {detail.url}
                </a>
              ) : (fallbackUrl || '—')}
            </div>
          </>
        )}
        {detail.url_title && (
          <>
            <div style={{ color: '#888' }}>Page title</div>
            <div>{detail.url_title}</div>
          </>
        )}
        <div style={{ color: '#888' }}>Status</div>
        <div>{detail.status}{detail.error_message ? ` — ${detail.error_message}` : ''}</div>
        <div style={{ color: '#888' }}>Chunks</div>
        <div>{detail.chunk_count}</div>
        {detail.crawl_enabled && (
          <>
            <div style={{ color: '#888' }}>Crawl</div>
            <div>up to {detail.max_crawl_pages} pages · {childCount} discovered</div>
          </>
        )}
        {detail.parent_source_uuid && (
          <>
            <div style={{ color: '#888' }}>Crawled from</div>
            <div style={{ fontFamily: 'monospace', fontSize: 11 }}>{detail.parent_source_uuid}</div>
          </>
        )}
        {detail.processed_at && (
          <>
            <div style={{ color: '#888' }}>Processed</div>
            <div>{new Date(detail.processed_at).toLocaleString()}</div>
          </>
        )}
      </div>

      {/* Crawled children list */}
      {childCount > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#ccc', marginBottom: 6 }}>
            Crawled pages ({childCount})
          </div>
          <div style={{
            display: 'flex', flexDirection: 'column', gap: 4,
            maxHeight: 160, overflowY: 'auto',
            border: '1px solid #2a2a2a', borderRadius: 6, padding: 8,
          }}>
            {detail.child_sources.map(c => (
              <a
                key={c.uuid}
                href={c.url || undefined}
                target="_blank"
                rel="noopener noreferrer"
                title={c.url}
                style={{
                  fontSize: 11, color: '#9ca3af', textDecoration: 'none',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}
              >
                {c.url_title || c.url}
              </a>
            ))}
          </div>
        </div>
      )}

      {/* Cached content */}
      <div style={{ fontSize: 12, fontWeight: 600, color: '#ccc', marginBottom: 6 }}>
        Extracted text
      </div>
      {hasContent ? (
        <pre style={{
          margin: 0, padding: 12, flex: 1,
          fontSize: 12, lineHeight: 1.55,
          color: '#d1d5db',
          backgroundColor: '#161616',
          border: '1px solid #2a2a2a', borderRadius: 6,
          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          overflowY: 'auto',
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
        }}>
          {detail.content}
        </pre>
      ) : (
        <div style={{ fontSize: 12, color: '#888', fontStyle: 'italic' }}>
          No cached text available for this source.
        </div>
      )}
    </div>
  )
}
