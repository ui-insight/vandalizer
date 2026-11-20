import { useState } from 'react'
import { ActionButton } from '../shared/ActionButton'

export interface UrlCandidate {
  url: string
  /** A page title (topic suggestions); the URL is shown when absent. */
  title?: string
  /** One more line: why it was suggested, or when the sitemap says it changed. */
  detail?: string | null
  /** The KB already holds it: shown, but can't be picked. */
  inKb?: boolean
}

// Rendering thousands of checkbox rows stalls the dialog; a filter narrows it.
const MAX_SHOWN = 500

interface UrlReviewListProps {
  candidates: UrlCandidate[]
  selected: Set<string>
  onChange: (next: Set<string>) => void
  disabled?: boolean
}

/** The review step of Add URLs: every found link, checked or not, before anything is added. */
export function UrlReviewList({ candidates, selected, onChange, disabled }: UrlReviewListProps) {
  const [filter, setFilter] = useState('')
  const needle = filter.trim().toLowerCase()
  const matching = needle
    ? candidates.filter(c => c.url.toLowerCase().includes(needle) || c.title?.toLowerCase().includes(needle))
    : candidates
  const shown = matching.slice(0, MAX_SHOWN)
  const pickable = matching.filter(c => !c.inKb)

  const setMany = (urls: string[], on: boolean) => {
    const next = new Set(selected)
    for (const url of urls) {
      if (on) next.add(url)
      else next.delete(url)
    }
    onChange(next)
  }

  const inKbCount = candidates.filter(c => c.inKb).length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-8)', minHeight: 0 }}>
      <div role="status" style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)' }}>
        {selected.size} of {candidates.length - inKbCount} selected
        {inKbCount > 0 && <span style={{ color: 'var(--workspace-muted)' }}> · {inKbCount} already in this knowledge base</span>}
      </div>
      {candidates.length > 10 && (
        <input
          type="search"
          aria-label="Filter links"
          placeholder="Filter, e.g. /grants/ or policy"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          style={{
            width: '100%', padding: 'var(--workspace-space-6) var(--workspace-space-8)', fontSize: 'var(--workspace-font-control)', fontFamily: 'inherit',
            backgroundColor: 'var(--workspace-surface)', color: 'var(--workspace-text)',
            border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-small)',
          }}
        />
      )}
      <div style={{ display: 'flex', gap: 'var(--workspace-space-8)' }}>
        <ActionButton variant="quiet" disabled={disabled || pickable.length === 0} onClick={() => setMany(pickable.map(c => c.url), true)}>
          {needle ? `Select ${pickable.length} shown` : 'Select all'}
        </ActionButton>
        <ActionButton variant="quiet" disabled={disabled || selected.size === 0} onClick={() => setMany(matching.map(c => c.url), false)}>
          {needle ? 'Clear shown' : 'Clear'}
        </ActionButton>
      </div>
      <ul aria-label="Links to add" style={{
        listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-6)',
        overflowY: 'auto', maxHeight: 320, minHeight: 0,
      }}>
        {shown.map(c => {
          const id = `url-review-${encodeURIComponent(c.url)}`
          return (
            <li key={c.url} style={{ display: 'flex', gap: 'var(--workspace-space-8)', alignItems: 'flex-start' }}>
              <input
                id={id}
                type="checkbox"
                disabled={disabled || c.inKb}
                checked={!c.inKb && selected.has(c.url)}
                onChange={e => setMany([c.url], e.target.checked)}
                style={{ marginTop: 3, accentColor: 'var(--workspace-accent-ink)' }}
              />
              <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
                <label htmlFor={id} style={{
                  fontSize: 'var(--workspace-font-control)', cursor: c.inKb ? 'default' : 'pointer', overflowWrap: 'anywhere',
                  color: c.inKb ? 'var(--workspace-muted)' : 'var(--workspace-text)', fontWeight: c.title ? 500 : 400,
                }}>
                  {c.title || c.url}
                </label>
                {c.title && (
                  <a href={c.url} target="_blank" rel="noopener noreferrer"
                    style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-accent-ink)', overflowWrap: 'anywhere' }}>
                    {c.url}
                  </a>
                )}
                {(c.inKb || c.detail) && (
                  <span style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', lineHeight: 1.4 }}>
                    {c.inKb ? 'Already in this knowledge base' : c.detail}
                  </span>
                )}
              </div>
            </li>
          )
        })}
        {matching.length > shown.length && (
          <li style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
            Showing {shown.length} of {matching.length}. Filter to find the rest; Select all includes them.
          </li>
        )}
        {matching.length === 0 && (
          <li style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-muted)' }}>No links match the filter.</li>
        )}
      </ul>
    </div>
  )
}
