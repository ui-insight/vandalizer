import { useState, useEffect, useCallback } from 'react'
import { X, Search, FileText, Loader2, Check } from 'lucide-react'
import { searchDocuments, type SearchResult } from '../../api/documents'

interface DocumentPickerModalProps {
  onSubmit: (docUuids: string[]) => void
  onClose: () => void
  existingSourceUuids?: string[]
}

export function DocumentPickerModal({ onSubmit, onClose, existingSourceUuids = [] }: DocumentPickerModalProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const doSearch = useCallback(async (q: string) => {
    setLoading(true)
    try {
      const data = await searchDocuments(q, 30)
      setResults(data.items.filter(d => !existingSourceUuids.includes(d.uuid)))
    } catch (err) {
      console.error('Search failed:', err)
    } finally {
      setLoading(false)
    }
  }, [existingSourceUuids])

  // Load initial results
  useEffect(() => {
    doSearch('')
  }, [doSearch])

  // Debounced search on query change
  useEffect(() => {
    if (!query) return
    const timer = setTimeout(() => doSearch(query), 300)
    return () => clearTimeout(timer)
  }, [query, doSearch])

  const toggleDoc = (uuid: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(uuid)) next.delete(uuid)
      else next.add(uuid)
      return next
    })
  }

  const handleSubmit = () => {
    if (selected.size > 0) {
      onSubmit(Array.from(selected))
    }
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        backgroundColor: 'rgba(0,0,0,0.6)',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: 520, maxHeight: '80vh',
          backgroundColor: '#1e1e1e', borderRadius: 12,
          border: '1px solid #3a3a3a', padding: 24,
          display: 'flex', flexDirection: 'column', gap: 16,
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 16, fontWeight: 600, color: '#fff' }}>Add Documents</span>
          <button
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 4, display: 'flex' }}
          >
            <X size={18} style={{ color: '#888' }} />
          </button>
        </div>

        {/* Search */}
        <div style={{ position: 'relative' }}>
          <Search size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#666' }} />
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search documents..."
            style={{
              width: '100%', padding: '10px 12px 10px 34px', fontSize: 13, fontFamily: 'inherit',
              backgroundColor: '#2a2a2a', color: '#e5e5e5',
              border: '1px solid #3a3a3a', borderRadius: 8, outline: 'none',
              boxSizing: 'border-box',
            }}
          />
        </div>

        {/* Results */}
        <div style={{ flex: 1, overflowY: 'auto', maxHeight: 360, minHeight: 120 }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 30, color: '#888' }}>
              <Loader2 style={{ width: 18, height: 18, margin: '0 auto', animation: 'spin 1s linear infinite' }} />
            </div>
          ) : results.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 30, color: '#888', fontSize: 13 }}>
              {query ? 'No documents found' : 'No documents available'}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {results.map(doc => {
                const isSelected = selected.has(doc.uuid)
                return (
                  <button
                    key={doc.uuid}
                    onClick={() => toggleDoc(doc.uuid)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      padding: '10px 12px', width: '100%', textAlign: 'left',
                      backgroundColor: isSelected ? '#2a3a2a' : '#2a2a2a',
                      border: isSelected ? '1px solid #4a7a4a' : '1px solid #3a3a3a',
                      borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit',
                      transition: 'background-color 0.1s',
                    }}
                  >
                    <div
                      style={{
                        width: 18, height: 18, borderRadius: 4, flexShrink: 0,
                        border: isSelected ? 'none' : '1px solid #555',
                        backgroundColor: isSelected ? 'var(--highlight-color, #eab308)' : 'transparent',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}
                    >
                      {isSelected && <Check size={12} style={{ color: '#000' }} />}
                    </div>
                    <FileText size={14} style={{ color: '#888', flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: 13, color: '#e5e5e5', overflow: 'hidden',
                        textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {doc.title}
                      </div>
                      <div style={{ fontSize: 11, color: '#888', marginTop: 2 }}>
                        {doc.extension.toUpperCase()}{doc.num_pages > 0 ? ` \u00b7 ${doc.num_pages} pages` : ''}
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: '#888' }}>
            {selected.size > 0 ? `${selected.size} selected` : ''}
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={onClose}
              style={{
                padding: '8px 16px', fontSize: 13, fontWeight: 500, fontFamily: 'inherit',
                color: '#ccc', backgroundColor: 'transparent',
                border: '1px solid #3a3a3a', borderRadius: 6, cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={selected.size === 0}
              style={{
                padding: '8px 16px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                color: '#000', backgroundColor: 'var(--highlight-color, #eab308)',
                border: 'none', borderRadius: 6,
                cursor: selected.size > 0 ? 'pointer' : 'default',
                opacity: selected.size > 0 ? 1 : 0.5,
              }}
            >
              Add {selected.size > 0 ? `(${selected.size})` : ''}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
