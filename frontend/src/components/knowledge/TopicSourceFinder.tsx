import { useEffect, useState } from 'react'
import { Loader2, Search } from 'lucide-react'
import { FieldLabel, FieldMessage } from '../shared/FormField'
import { ActionButton } from '../shared/ActionButton'
import { getSourceSuggestionsAvailable, suggestSources } from '../../api/knowledge'
import type { SourceSuggestion } from '../../api/knowledge'

interface TopicSourceFinderProps {
  kbUuid: string
  /** URLs currently in the Add URLs list; a checked suggestion is one of them. */
  selectedUrls: Set<string>
  onToggle: (url: string, checked: boolean) => void
  disabled?: boolean
}

/**
 * "Find pages by topic" for Add URLs: describe what the knowledge base should
 * cover and check the suggested pages to add (feature request — building a KB
 * meant hunting down every link by hand). A checked page goes into the URL
 * list above Add, so it is added exactly like a pasted one, crawl options and
 * all. Every suggestion is a web-search result; hidden where web search isn't
 * configured, since there would be nothing to ground them in.
 */
export function TopicSourceFinder({ kbUuid, selectedUrls, onToggle, disabled }: TopicSourceFinderProps) {
  const [available, setAvailable] = useState(false)
  const [topic, setTopic] = useState('')
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<SourceSuggestion[] | null>(null)
  const [alreadyInKb, setAlreadyInKb] = useState(0)

  useEffect(() => {
    let cancelled = false
    getSourceSuggestionsAvailable(kbUuid)
      .then(r => { if (!cancelled) setAvailable(r.available) })
      .catch(() => { if (!cancelled) setAvailable(false) })
    return () => { cancelled = true }
  }, [kbUuid])

  if (!available) return null

  const canSearch = topic.trim().length >= 3 && !searching && !disabled

  const search = async () => {
    if (!canSearch) return
    setSearching(true)
    setError(null)
    try {
      const result = await suggestSources(kbUuid, topic.trim())
      setSuggestions(result.suggestions)
      setAlreadyInKb(result.already_in_kb)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not search for pages')
    } finally {
      setSearching(false)
    }
  }

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-8)',
      padding: 'var(--workspace-space-12)', borderRadius: 'var(--workspace-radius-medium)',
      border: '1px solid var(--workspace-border)', backgroundColor: 'var(--workspace-surface)', flexShrink: 0,
    }}>
      <FieldLabel htmlFor="topic-source-input" optional>Find pages by topic</FieldLabel>
      <div style={{ display: 'flex', gap: 'var(--workspace-space-8)' }}>
        <input
          id="topic-source-input"
          type="text"
          value={topic}
          disabled={disabled || searching}
          onChange={e => setTopic(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); void search() } }}
          placeholder="e.g. NSF proposal requirements"
          maxLength={300}
          style={{
            flex: 1, minWidth: 0, padding: 'var(--workspace-space-6) var(--workspace-space-8)',
            fontSize: 'var(--workspace-font-control)', fontFamily: 'inherit',
            backgroundColor: 'var(--workspace-canvas)', color: 'var(--workspace-text)',
            border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-small)',
          }}
        />
        <ActionButton variant="secondary" onClick={search} disabled={!canSearch} aria-busy={searching}>
          {searching ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <Search size={14} aria-hidden="true" />}
          {searching ? 'Searching…' : 'Find pages'}
        </ActionButton>
      </div>
      <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
        Searches the web and suggests pages. Check the ones to add; they join the list below.
      </div>

      {error && <FieldMessage id="topic-source-error" error>{error}</FieldMessage>}

      {suggestions && suggestions.length === 0 && (
        <div role="status" style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-muted)' }}>
          {alreadyInKb > 0
            ? `No new pages found — the ${alreadyInKb} page${alreadyInKb === 1 ? '' : 's'} found ${alreadyInKb === 1 ? 'is' : 'are'} already in this knowledge base.`
            : 'No pages found. Try describing the topic differently.'}
        </div>
      )}

      {suggestions && suggestions.length > 0 && (
        <ul aria-label="Suggested pages" style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-8)' }}>
          {suggestions.map(s => {
            const id = `topic-source-${encodeURIComponent(s.url)}`
            return (
              <li key={s.url} style={{ display: 'flex', gap: 'var(--workspace-space-8)', alignItems: 'flex-start' }}>
                <input
                  id={id}
                  type="checkbox"
                  disabled={disabled}
                  checked={selectedUrls.has(s.url)}
                  onChange={e => onToggle(s.url, e.target.checked)}
                  style={{ marginTop: 3, accentColor: 'var(--workspace-accent-ink)' }}
                />
                <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <label htmlFor={id} style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)', fontWeight: 500, cursor: 'pointer', overflowWrap: 'anywhere' }}>
                    {s.title}
                  </label>
                  <a href={s.url} target="_blank" rel="noopener noreferrer"
                    style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-accent-ink)', overflowWrap: 'anywhere' }}>
                    {s.host || s.url}
                  </a>
                  {(s.reason || s.snippet) && (
                    <span style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', lineHeight: 1.4 }}>
                      {s.reason || s.snippet}
                    </span>
                  )}
                </div>
              </li>
            )
          })}
          {alreadyInKb > 0 && (
            <li style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
              {alreadyInKb} more page{alreadyInKb === 1 ? '' : 's'} found {alreadyInKb === 1 ? 'is' : 'are'} already in this knowledge base.
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
