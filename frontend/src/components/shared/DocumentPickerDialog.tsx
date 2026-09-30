import { useEffect, useId, useState } from 'react'
import { FocusTrap } from './PanelFocusTrap'
import { X, Loader2, FileText } from 'lucide-react'
import { searchDocuments } from '../../api/documents'
import { ActionButton } from './ActionButton'
import { FieldLabel, FieldMessage } from './FormField'

type DocumentChoice = { uuid: string; title: string }

export function DocumentPickerDialog({ onSelect, onClose, excludeUuids, title = 'Add Documents', zIndex = 1000 }: {
  onSelect: (docs: DocumentChoice[]) => void
  onClose: () => void
  excludeUuids: string[]
  title?: string
  zIndex?: number
}) {
  const id = useId()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<DocumentChoice[]>([])
  const [searching, setSearching] = useState(true)
  const [error, setError] = useState(false)
  const [retry, setRetry] = useState(0)
  const [selected, setSelected] = useState<Map<string, DocumentChoice>>(new Map())
  const excluded = JSON.stringify(excludeUuids)

  useEffect(() => {
    let current = true
    setSearching(true)
    setError(false)
    const timer = setTimeout(() => {
      searchDocuments(query, 30).then(res => {
        if (current) setResults(res.items.filter(d => !JSON.parse(excluded).includes(d.uuid)).map(d => ({ uuid: d.uuid, title: d.title })))
      }).catch(() => { if (current) setError(true) })
        .finally(() => { if (current) setSearching(false) })
    }, 300)
    return () => { current = false; clearTimeout(timer) }
  }, [query, excluded, retry])

  return <div className="workspace-dialog-backdrop" style={{ zIndex }}>
    <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, initialFocus: () => document.getElementById(`${id}-search`)!, tabbableOptions: { displayCheck: import.meta.env.MODE === 'test' ? 'none' : 'full' } }}>
      <div role="dialog" aria-modal="true" aria-labelledby={`${id}-title`} className="workspace-dialog" style={{ width: 480 }} onKeyDown={event => {
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); onClose() }
      }}>
        <div className="workspace-dialog-header">
          <h3 id={`${id}-title`}>{title}</h3>
          <ActionButton variant="quiet" iconOnly aria-label="Close document picker" onClick={onClose}><X size={18} /></ActionButton>
        </div>
        <div className="workspace-dialog-body">
          <FieldLabel htmlFor={`${id}-search`}>Search documents</FieldLabel>
          <input id={`${id}-search`} value={query} onChange={e => setQuery(e.target.value)} placeholder="Search documents..." style={{ width: '100%', padding: 8, border: '1px solid var(--workspace-border)', borderRadius: 6 }} />
          <p role="status" aria-atomic="true" className="workspace-field-message">{searching ? 'Searching documents…' : error ? 'Search unavailable.' : `${results.length} documents shown. ${selected.size} selected.`}</p>
          {searching ? <Loader2 size={18} aria-hidden="true" className="animate-spin" /> : error ? <div>
            <FieldMessage id={`${id}-error`} error>Your selections are preserved. Try searching again.</FieldMessage>
            <ActionButton variant="secondary" onClick={() => setRetry(n => n + 1)}>Retry search</ActionButton>
          </div> : results.length === 0 ? <p>No documents found. Try a different search.</p> : results.map(doc => <label key={doc.uuid} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 0', borderBottom: '1px solid var(--workspace-border)' }}>
            <input type="checkbox" checked={selected.has(doc.uuid)} onChange={() => setSelected(previous => {
              const next = new Map(previous)
              if (next.has(doc.uuid)) next.delete(doc.uuid)
              else next.set(doc.uuid, doc)
              return next
            })} />
            <FileText size={16} aria-hidden="true" style={{ flexShrink: 0 }} />
            <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>{doc.title}</span>
          </label>)}
        </div>
        <div className="workspace-dialog-footer">
          <ActionButton variant="secondary" onClick={onClose}>Cancel</ActionButton>
          <ActionButton variant="primary" disabled={selected.size === 0} onClick={() => { onSelect([...selected.values()]); onClose() }}>Add {selected.size > 0 ? `${selected.size} ` : ''}Selected</ActionButton>
        </div>
      </div>
    </FocusTrap>
  </div>
}
