import { useCallback, useEffect, useState } from 'react'
import { X, Search, Loader2, FileText } from 'lucide-react'
import { searchDocuments } from '../../api/documents'

export function DocumentPickerDialog({
  onSelect,
  onClose,
  excludeUuids,
}: {
  onSelect: (docs: { uuid: string; title: string }[]) => void
  onClose: () => void
  excludeUuids: string[]
}) {
  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState<{ uuid: string; title: string }[]>([])
  const [searching, setSearching] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const excludeRef = useCallback((uuid: string) => excludeUuids.includes(uuid), [excludeUuids.join(',')])

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearching(true)
      searchDocuments(query, 30)
        .then(res => {
          setSearchResults(
            res.items
              .filter(d => !excludeRef(d.uuid))
              .map(d => ({ uuid: d.uuid, title: d.title }))
          )
        })
        .catch(() => setSearchResults([]))
        .finally(() => setSearching(false))
    }, 300)
    return () => clearTimeout(timer)
  }, [query, excludeRef])

  const toggleDoc = (uuid: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(uuid)) next.delete(uuid)
      else next.add(uuid)
      return next
    })
  }

  const handleAdd = () => {
    const docs = searchResults.filter(d => selected.has(d.uuid))
    onSelect(docs)
    onClose()
  }

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: 'rgba(0,0,0,0.3)', display: 'flex', alignItems: 'center',
      justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{
        backgroundColor: '#fff', borderRadius: 12, width: 480, maxHeight: '70vh',
        display: 'flex', flexDirection: 'column', boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
      }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 15, fontWeight: 600, color: '#202124' }}>Add Documents</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#5f6368', display: 'flex' }}>
            <X style={{ width: 18, height: 18 }} />
          </button>
        </div>
        <div style={{ padding: '12px 20px', borderBottom: '1px solid #e5e7eb' }}>
          <div style={{ position: 'relative' }}>
            <Search style={{ width: 14, height: 14, position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#9ca3af' }} />
            <input
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search documents..."
              style={{
                width: '100%', fontSize: 13, fontFamily: 'inherit',
                border: '1px solid #d1d5db', borderRadius: 6, padding: '8px 10px 8px 32px',
                outline: 'none', boxSizing: 'border-box',
              }}
            />
          </div>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 20px', minHeight: 200, maxHeight: 400 }}>
          {searching ? (
            <div style={{ textAlign: 'center', color: '#888', fontSize: 13, padding: '24px 0' }}>
              <Loader2 style={{ width: 16, height: 16, animation: 'spin 1s linear infinite', display: 'inline-block' }} />
            </div>
          ) : searchResults.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#888', fontSize: 13, padding: '24px 0' }}>
              {query ? 'No documents found.' : 'Type to search documents...'}
            </div>
          ) : (
            searchResults.map(doc => (
              <label key={doc.uuid} style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0',
                borderBottom: '1px solid #f0f0f0', cursor: 'pointer',
              }}>
                <input
                  type="checkbox"
                  checked={selected.has(doc.uuid)}
                  onChange={() => toggleDoc(doc.uuid)}
                />
                <FileText style={{ width: 14, height: 14, color: '#6b7280', flexShrink: 0 }} />
                <span style={{ fontSize: 13, color: '#202124', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {doc.title}
                </span>
              </label>
            ))
          )}
        </div>
        <div style={{ padding: '12px 20px', borderTop: '1px solid #e5e7eb', display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 16px', fontSize: 13, fontWeight: 500, fontFamily: 'inherit',
              borderRadius: 6, border: '1px solid #d1d5db', backgroundColor: '#fff',
              color: '#374151', cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleAdd}
            disabled={selected.size === 0}
            style={{
              padding: '8px 16px', fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
              borderRadius: 6, border: 'none',
              backgroundColor: selected.size > 0 ? '#191919' : '#e5e7eb',
              color: selected.size > 0 ? '#fff' : '#9ca3af',
              cursor: selected.size > 0 ? 'pointer' : 'not-allowed',
            }}
          >
            Add {selected.size > 0 ? `${selected.size} ` : ''}Selected
          </button>
        </div>
      </div>
    </div>
  )
}
