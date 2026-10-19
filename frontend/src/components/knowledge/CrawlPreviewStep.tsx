import { Loader2, X } from 'lucide-react'
import type { CrawlPreview } from '../../api/knowledge'
import { formatChars, groupByStart, isSelectable, pageLabel } from './crawlPreview'

/** Step two of a crawl: the pages it found, ticked to choose which to add. */
export function CrawlPreviewStep({
  preview, selected, onChange, error, adding, onAdd, onBack, onClose,
}: {
  preview: CrawlPreview
  selected: Set<string>
  onChange: (next: Set<string>) => void
  error: string | null
  adding: boolean
  onAdd: () => void
  onBack: () => void
  onClose: () => void
}) {
  const running = preview.status === 'running'
  const selectable = preview.pages.filter(isSelectable)
  const found = preview.pages.filter(p => p.kind === 'content' && !p.in_kb).length
  const toggle = (url: string) => {
    const next = new Set(selected)
    if (next.has(url)) next.delete(url)
    else next.add(url)
    onChange(next)
  }
  const n = selected.size
  const canAdd = preview.status === 'complete' && n > 0 && !adding
  const linkButton: React.CSSProperties = {
    padding: 0, background: 'transparent', border: 'none', fontSize: 12,
    fontFamily: 'inherit', color: '#7aa2f7', cursor: 'pointer',
  }

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 16, fontWeight: 600, color: '#fff' }}>Choose pages to add</span>
        <button
          onClick={onClose}
          aria-label="Close"
          style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 4, display: 'flex' }}
        >
          <X size={18} style={{ color: '#888' }} />
        </button>
      </div>
      <div style={{ fontSize: 13, color: '#aaa', lineHeight: 1.5 }} aria-live="polite">
        {running ? (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} />
            Finding pages… {preview.fetched} fetched, {found} of up to {preview.max_crawl_pages} content pages found per URL.
          </span>
        ) : preview.status === 'error' ? (
          <span style={{ color: '#ef4444' }}>{preview.error_message || 'The crawl preview stopped.'}</span>
        ) : (
          <>Found {preview.pages.length} {preview.pages.length === 1 ? 'page' : 'pages'}. Nothing has been added yet — tick the pages to include. Pages that look like site navigation start unticked.</>
        )}
      </div>

      {selectable.length > 0 && (
        <div style={{ display: 'flex', gap: 12 }}>
          <button type="button" style={linkButton} onClick={() => onChange(new Set(selectable.map(p => p.url)))}>Select all</button>
          <button type="button" style={linkButton} onClick={() => onChange(new Set())}>Select none</button>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto', maxHeight: '45vh' }}>
        {groupByStart(preview.start_urls, preview.pages).map(group => (
          <div key={group.start} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {preview.start_urls.length > 1 && (
              <div style={{ fontSize: 11, color: '#888', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                From {group.start}
              </div>
            )}
            {group.pages.map(p => {
              const can = isSelectable(p)
              const label = pageLabel(p)
              return (
                <label
                  key={p.url}
                  style={{
                    display: 'flex', gap: 8, alignItems: 'flex-start', padding: '6px 8px',
                    backgroundColor: '#2a2a2a', border: '1px solid #3a3a3a', borderRadius: 6,
                    cursor: can ? 'pointer' : 'default', opacity: can ? 1 : 0.6,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={can && selected.has(p.url)}
                    disabled={!can}
                    onChange={() => toggle(p.url)}
                    aria-label={`Add ${p.title || p.url}`}
                    style={{ marginTop: 2, accentColor: 'var(--highlight-color, #eab308)' }}
                  />
                  <span style={{ minWidth: 0, flex: 1 }}>
                    <span style={{ display: 'block', fontSize: 12, color: '#e5e5e5', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.title || p.url}
                    </span>
                    <span style={{ display: 'block', fontSize: 11, color: '#9a9a9a', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={p.url}>
                      {p.url}
                    </span>
                    {(label || p.chars > 0) && (
                      <span style={{ display: 'block', fontSize: 11, color: p.kind === 'navigation' || p.kind === 'failed' ? '#d97706' : '#888' }}>
                        {[label, p.chars > 0 ? formatChars(p.chars) : ''].filter(Boolean).join(' · ')}
                      </span>
                    )}
                  </span>
                </label>
              )
            })}
          </div>
        ))}
      </div>

      {error && <div role="alert" style={{ fontSize: 12, color: '#ef4444' }}>{error}</div>}

      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
        <button
          onClick={onBack}
          disabled={adding}
          style={{
            padding: '8px 16px', fontSize: 13, fontWeight: 500, fontFamily: 'inherit',
            color: '#ccc', backgroundColor: 'transparent',
            border: '1px solid #3a3a3a', borderRadius: 6, cursor: 'pointer',
          }}
        >
          Back
        </button>
        <button
          onClick={onAdd}
          disabled={!canAdd}
          style={{
            padding: '8px 16px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
            color: 'var(--highlight-text-color, #000)', backgroundColor: 'var(--highlight-color, #eab308)',
            border: 'none', borderRadius: 6,
            cursor: canAdd ? 'pointer' : 'default', opacity: canAdd ? 1 : 0.5,
          }}
        >
          {adding ? 'Adding…' : `Add ${n} ${n === 1 ? 'page' : 'pages'}`}
        </button>
      </div>
    </>
  )
}
