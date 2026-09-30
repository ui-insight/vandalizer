import { useState, useCallback, useRef, useEffect } from 'react'
import { Search, X, FileText } from 'lucide-react'
import { searchDocuments } from '../../api/documents'
import type { SearchResult } from '../../api/documents'

interface GlobalSearchProps {
  onDocClick?: (doc: { uuid: string; title: string }) => void
}

export function GlobalSearch({ onDocClick }: GlobalSearchProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const handleSearch = useCallback((q: string) => {
    if (!q.trim()) {
      setResults([])
      setSearched(false)
      return
    }
    setLoading(true)
    setSearched(true)
    searchDocuments(q.trim())
      .then(r => setResults(r.items))
      .catch(() => setResults([]))
      .finally(() => setLoading(false))
  }, [])

  const handleChange = (value: string) => {
    setQuery(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => handleSearch(value), 400)
  }

  const handleClose = () => {
    setOpen(false)
    setQuery('')
    setResults([])
    setSearched(false)
  }

  const handleSelect = (doc: SearchResult) => {
    onDocClick?.({ uuid: doc.uuid, title: doc.title })
    handleClose()
  }

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          width: 32, height: 32, borderRadius: 'var(--workspace-radius-small)', border: 'none',
          background: 'none', cursor: 'pointer', color: '#fff',
        }}
        aria-label="Search documents"
      >
        <Search size={16} />
      </button>
    )
  }

  return (
    <div style={{
      position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 500,
      display: 'flex', flexDirection: 'column', backgroundColor: '#fff',
    }}>
      {/* Search header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', padding: "var(--workspace-space-8) var(--workspace-space-12)",
        borderBottom: "1px solid var(--workspace-border)", backgroundColor: '#f9fafb',
      }}>
        <Search size={18} color="#6b7280" />
        <input
          ref={inputRef}
          value={query}
          onChange={e => handleChange(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Escape') handleClose()
          }}
          placeholder="Search document titles and content..."
          aria-label="Search documents"
          onFocus={e => { e.currentTarget.style.boxShadow = '0 0 0 2px var(--highlight-color, #eab308)' }}
          onBlur={e => { e.currentTarget.style.boxShadow = 'none' }}
          style={{
            flex: 1, border: 'none', background: 'none', outline: 'none',
            fontSize: 'var(--workspace-font-card-title)', color: '#111827', borderRadius: 'var(--workspace-radius-small)',
          }}
        />
        <button
          onClick={handleClose}
          aria-label="Close search"
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', padding: 'var(--workspace-space-4)' }}
        >
          <X size={18} />
        </button>
      </div>

      {/* Results */}
      <div style={{ flex: 1, overflow: 'auto', padding: "var(--workspace-space-8) 0" }}>
        <div aria-live="polite" className="sr-only">
          {loading
            ? 'Searching'
            : searched
              ? `${results.length} result${results.length !== 1 ? 's' : ''} found`
              : ''}
        </div>
        {loading && (
          <div role="status" aria-live="polite" style={{ padding: "var(--workspace-space-20) var(--workspace-space-16)", textAlign: 'center', color: '#6b7280', fontSize: 'var(--workspace-font-body)' }}>Searching...</div>
        )}

        {!loading && searched && results.length === 0 && (
          <div role="status" aria-live="polite" style={{ padding: "30px var(--workspace-space-16)", textAlign: 'center', color: '#6b7280', fontSize: 'var(--workspace-font-body)' }}>
            No documents found for "{query}"
          </div>
        )}

        {!loading && results.map(doc => (
          <button
            key={doc.uuid}
            onClick={() => handleSelect(doc)}
            style={{
              display: 'flex', alignItems: 'flex-start', gap: 'var(--workspace-space-12)', width: '100%',
              padding: "var(--workspace-space-12) var(--workspace-space-16)", border: 'none', background: 'transparent',
              cursor: 'pointer', textAlign: 'left',
            }}
            onMouseEnter={e => { e.currentTarget.style.backgroundColor = '#f3f4f6' }}
            onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent' }}
          >
            <FileText size={18} color="#6b7280" style={{ marginTop: 'var(--workspace-space-2)', flexShrink: 0 }} aria-hidden="true" />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 'var(--workspace-font-body)', fontWeight: 500, color: '#111827' }}>{doc.title}</div>
              {doc.snippet && (
                <div style={{
                  fontSize: 'var(--workspace-font-meta)', color: '#6b7280', marginTop: 'var(--workspace-space-2)',
                  overflow: 'hidden', textOverflow: 'ellipsis',
                  display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                }}>
                  {doc.snippet}
                </div>
              )}
              <div style={{ fontSize: 'var(--workspace-font-meta)', color: '#6b7280', marginTop: 'var(--workspace-space-4)' }}>
                {doc.extension.toUpperCase()} · {doc.num_pages} page{doc.num_pages !== 1 ? 's' : ''}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
