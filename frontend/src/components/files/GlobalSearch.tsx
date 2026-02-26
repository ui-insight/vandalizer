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
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()

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
          width: 32, height: 32, borderRadius: 6, border: 'none',
          background: 'none', cursor: 'pointer', color: '#fff',
        }}
        title="Search documents"
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
        display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
        borderBottom: '1px solid #e5e7eb', backgroundColor: '#f9fafb',
      }}>
        <Search size={18} color="#6b7280" />
        <input
          ref={inputRef}
          value={query}
          onChange={e => handleChange(e.target.value)}
          placeholder="Search document titles and content..."
          style={{
            flex: 1, border: 'none', background: 'none', outline: 'none',
            fontSize: 15, color: '#111827',
          }}
        />
        <button
          onClick={handleClose}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', padding: 4 }}
        >
          <X size={18} />
        </button>
      </div>

      {/* Results */}
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
        {loading && (
          <div style={{ padding: '20px 16px', textAlign: 'center', color: '#9ca3af', fontSize: 14 }}>Searching...</div>
        )}

        {!loading && searched && results.length === 0 && (
          <div style={{ padding: '30px 16px', textAlign: 'center', color: '#9ca3af', fontSize: 14 }}>
            No documents found for "{query}"
          </div>
        )}

        {!loading && results.map(doc => (
          <button
            key={doc.uuid}
            onClick={() => handleSelect(doc)}
            style={{
              display: 'flex', alignItems: 'flex-start', gap: 12, width: '100%',
              padding: '10px 16px', border: 'none', background: 'transparent',
              cursor: 'pointer', textAlign: 'left',
            }}
            onMouseEnter={e => { e.currentTarget.style.backgroundColor = '#f3f4f6' }}
            onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent' }}
          >
            <FileText size={18} color="#9ca3af" style={{ marginTop: 2, flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 500, color: '#111827' }}>{doc.title}</div>
              {doc.snippet && (
                <div style={{
                  fontSize: 12, color: '#6b7280', marginTop: 2,
                  overflow: 'hidden', textOverflow: 'ellipsis',
                  display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                }}>
                  {doc.snippet}
                </div>
              )}
              <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>
                {doc.extension.toUpperCase()} · {doc.num_pages} page{doc.num_pages !== 1 ? 's' : ''}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
