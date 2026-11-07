import { useState } from 'react'
import { Loader2, Search } from 'lucide-react'
import { FieldLabel, FieldMessage } from '../shared/FormField'
import { ActionButton } from '../shared/ActionButton'
import { suggestSources } from '../../api/knowledge'
import type { SourceSuggestion } from '../../api/knowledge'

interface TopicSourceFinderProps {
  kbUuid: string
  /** Called with the suggestions; Add URLs' review step picks among them. */
  onResults: (suggestions: SourceSuggestion[], alreadyInKb: number) => void
  disabled?: boolean
}

/**
 * The Topic way into Add URLs: describe what the knowledge base should cover
 * and get suggested pages to review (feature request — building a KB meant
 * hunting down every link by hand). Every suggestion is a web-search result;
 * Add URLs offers this only where web search is configured.
 */
export function TopicSourceFinder({ kbUuid, onResults, disabled }: TopicSourceFinderProps) {
  const [topic, setTopic] = useState('')
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [emptyNote, setEmptyNote] = useState<string | null>(null)

  const canSearch = topic.trim().length >= 3 && !searching && !disabled

  const search = async () => {
    if (!canSearch) return
    setSearching(true)
    setError(null)
    setEmptyNote(null)
    try {
      const result = await suggestSources(kbUuid, topic.trim())
      if (result.suggestions.length === 0) {
        const n = result.already_in_kb
        setEmptyNote(n > 0
          ? `No new pages found — the ${n} page${n === 1 ? '' : 's'} found ${n === 1 ? 'is' : 'are'} already in this knowledge base.`
          : 'No pages found. Try describing the topic differently.')
      } else {
        onResults(result.suggestions, result.already_in_kb)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not search for pages')
    } finally {
      setSearching(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-8)' }}>
      <FieldLabel htmlFor="topic-source-input" required>Topic</FieldLabel>
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
            backgroundColor: 'var(--workspace-surface)', color: 'var(--workspace-text)',
            border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-small)',
          }}
        />
        <ActionButton variant="secondary" onClick={search} disabled={!canSearch} aria-busy={searching}>
          {searching ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <Search size={14} aria-hidden="true" />}
          {searching ? 'Searching…' : 'Find pages'}
        </ActionButton>
      </div>
      <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
        Searches the web for pages on the topic; you choose which to add on the next step.
      </div>
      {error && <FieldMessage id="topic-source-error" error>{error}</FieldMessage>}
      {emptyNote && <div role="status" style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-muted)' }}>{emptyNote}</div>}
    </div>
  )
}
