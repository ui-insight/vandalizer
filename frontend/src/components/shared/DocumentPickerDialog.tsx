import { usePanelEffect } from './usePanelEffect'
import { useCallback, useEffect, useState } from 'react'
import { FocusTrap } from './PanelFocusTrap'
import { X, Search, Loader2, FileText } from 'lucide-react'
import { searchDocuments } from '../../api/documents'

export function DocumentPickerDialog({
  onSelect,
  onClose,
  excludeUuids,
  title = 'Add Documents',
  zIndex = 1000,
}: {
  onSelect: (docs: { uuid: string; title: string }[]) => void
  onClose: () => void
  excludeUuids: string[]
  /** Dialog heading — say where the documents come from when it isn't obvious. */
  title?: string
  /** Stacking order — raise it when opening from inside another modal. */
  zIndex?: number
}) {
  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState<{ uuid: string; title: string }[]>([])
  const [searching, setSearching] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const excludeRef = useCallback((uuid: string) => excludeUuids.includes(uuid), [excludeUuids.join(',')])

  usePanelEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

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
      justifyContent: 'center', zIndex,
    }}>
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div role="dialog" aria-modal="true" aria-label={title} style={{
        backgroundColor: '#fff', borderRadius: 'var(--workspace-radius-large)', width: 480, maxHeight: '70vh',
        display: 'flex', flexDirection: 'column', boxShadow: 'var(--workspace-shadow-dialog)',
      }}>
        <div style={{ padding: "var(--workspace-space-16) var(--workspace-space-20)", borderBottom: "1px solid var(--workspace-border)", display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 'var(--workspace-font-card-title)', fontWeight: 600, color: '#202124' }}>{title}</span>
          <button type="button" aria-label="Close" onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 'var(--workspace-space-4)', color: '#5f6368', display: 'flex' }}>
            <X style={{ width: 18, height: 18 }} />
          </button>
        </div>
        <div style={{ padding: "var(--workspace-space-12) var(--workspace-space-20)", borderBottom: "1px solid var(--workspace-border)" }}>
          <div style={{ position: 'relative' }}>
            <Search style={{ width: 14, height: 14, position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#6b7280' }} />
            <input
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search documents..."
              style={{
                width: '100%', fontSize: 'var(--workspace-font-control)', fontFamily: 'inherit',
                border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-8) var(--workspace-space-12) var(--workspace-space-8) var(--workspace-space-32)",
                boxSizing: 'border-box',
              }}
            />
          </div>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: "var(--workspace-space-8) var(--workspace-space-20)", minHeight: 200, maxHeight: 400 }}>
          {searching ? (
            <div style={{ textAlign: 'center', color: '#888', fontSize: 'var(--workspace-font-control)', padding: "var(--workspace-space-24) 0" }}>
              <Loader2 style={{ width: 16, height: 16, animation: 'spin 1s linear infinite', display: 'inline-block' }} />
            </div>
          ) : searchResults.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#888', fontSize: 'var(--workspace-font-control)', padding: "var(--workspace-space-24) 0" }}>
              {query ? 'No documents found.' : 'Type to search documents...'}
            </div>
          ) : (
            searchResults.map(doc => (
              <label key={doc.uuid} style={{
                display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', padding: "var(--workspace-space-8) 0",
                borderBottom: '1px solid #f0f0f0', cursor: 'pointer',
              }}>
                <input
                  type="checkbox"
                  checked={selected.has(doc.uuid)}
                  onChange={() => toggleDoc(doc.uuid)}
                />
                <FileText style={{ width: 14, height: 14, color: '#6b7280', flexShrink: 0 }} />
                <span style={{ fontSize: 'var(--workspace-font-control)', color: '#202124', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {doc.title}
                </span>
              </label>
            ))
          )}
        </div>
        <div style={{ padding: "var(--workspace-space-12) var(--workspace-space-20)", borderTop: "1px solid var(--workspace-border)", display: 'flex', justifyContent: 'flex-end', gap: 'var(--workspace-space-8)' }}>
          <button
            onClick={onClose}
            style={{
              padding: "var(--workspace-space-8) var(--workspace-space-16)", fontSize: 'var(--workspace-font-control)', fontWeight: 500, fontFamily: 'inherit',
              borderRadius: 'var(--workspace-radius-small)', border: "1px solid var(--workspace-border)", backgroundColor: '#fff',
              color: '#374151', cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleAdd}
            disabled={selected.size === 0}
            style={{
              padding: "var(--workspace-space-8) var(--workspace-space-16)", fontSize: 'var(--workspace-font-control)', fontWeight: 700, fontFamily: 'inherit',
              borderRadius: 'var(--workspace-radius-small)', border: 'none',
              backgroundColor: selected.size > 0 ? 'var(--color-panel-dark)' : '#e5e7eb',
              color: selected.size > 0 ? '#fff' : '#6b7280',
              cursor: selected.size > 0 ? 'pointer' : 'not-allowed',
            }}
          >
            Add {selected.size > 0 ? `${selected.size} ` : ''}Selected
          </button>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
