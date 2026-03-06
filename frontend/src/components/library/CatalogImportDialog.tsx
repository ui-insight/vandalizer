import { useState } from 'react'
import { X, Search, Loader2 } from 'lucide-react'
import { importCatalogItems } from '../../api/library'
import type { CatalogPreviewItem } from '../../api/library'

function KindBadge({ kind }: { kind: string }) {
  const isWorkflow = kind === 'workflow'
  return (
    <span
      style={{
        fontSize: 11,
        padding: '1px 6px',
        borderRadius: 4,
        border: `1px solid ${isWorkflow ? '#e9d5ff' : '#ccfbf1'}`,
        backgroundColor: isWorkflow ? '#faf5ff' : '#f0fdfa',
        color: isWorkflow ? '#7c3aed' : '#0f766e',
      }}
    >
      {isWorkflow ? 'Workflow' : 'Extraction'}
    </span>
  )
}

export function CatalogImportDialog({
  items,
  file,
  onClose,
  onImported,
}: {
  items: CatalogPreviewItem[]
  file: File
  onClose: () => void
  onImported: () => void
}) {
  const [selected, setSelected] = useState<Set<number>>(new Set(items.map(i => i.index)))
  const [search, setSearch] = useState('')
  const [importing, setImporting] = useState(false)

  const toggle = (idx: number) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  const toggleAll = () => {
    const filtered = filteredItems.map(i => i.index)
    const allSelected = filtered.every(i => selected.has(i))
    setSelected(prev => {
      const next = new Set(prev)
      for (const i of filtered) {
        if (allSelected) next.delete(i)
        else next.add(i)
      }
      return next
    })
  }

  const filteredItems = items.filter(item => {
    if (!search) return true
    const q = search.toLowerCase()
    return item.name.toLowerCase().includes(q) || item.description.toLowerCase().includes(q)
  })

  const handleImport = async () => {
    setImporting(true)
    try {
      await importCatalogItems(file, Array.from(selected), 'default')
      onImported()
    } catch (err: any) {
      alert(err.message || 'Import failed')
    } finally {
      setImporting(false)
    }
  }

  return (
    <div
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: 'rgba(0,0,0,0.3)', display: 'flex', alignItems: 'center',
        justifyContent: 'center', zIndex: 1000,
      }}
    >
      <div
        style={{
          backgroundColor: '#fff', borderRadius: 12, width: 520, maxHeight: '70vh',
          display: 'flex', flexDirection: 'column', boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
        }}
      >
        {/* Header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 15, fontWeight: 600, color: '#202124' }}>Import from Catalog</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#5f6368', display: 'flex' }}>
            <X style={{ width: 18, height: 18 }} />
          </button>
        </div>

        {/* Search */}
        <div style={{ padding: '12px 20px', borderBottom: '1px solid #e5e7eb' }}>
          <div style={{ position: 'relative' }}>
            <Search style={{ width: 14, height: 14, position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#9ca3af' }} />
            <input
              autoFocus
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Filter items..."
              style={{
                width: '100%', fontSize: 13, fontFamily: 'inherit',
                border: '1px solid #d1d5db', borderRadius: 6, padding: '8px 10px 8px 32px',
                outline: 'none', boxSizing: 'border-box',
              }}
            />
          </div>
        </div>

        {/* Item list */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 20px', minHeight: 200, maxHeight: 400 }}>
          {/* Select all */}
          <label style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0',
            borderBottom: '1px solid #e5e7eb', cursor: 'pointer', fontSize: 12, color: '#6b7280', fontWeight: 500,
          }}>
            <input
              type="checkbox"
              checked={filteredItems.length > 0 && filteredItems.every(i => selected.has(i.index))}
              onChange={toggleAll}
            />
            Select all ({filteredItems.length})
          </label>
          {filteredItems.map(item => (
            <label
              key={item.index}
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 8, padding: '10px 0',
                borderBottom: '1px solid #f0f0f0', cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={selected.has(item.index)}
                onChange={() => toggle(item.index)}
                style={{ marginTop: 3 }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                  <span style={{ fontSize: 13, fontWeight: 500, color: '#202124', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.name}
                  </span>
                  <KindBadge kind={item.item_kind} />
                  {item.quality_tier && (
                    <span style={{ fontSize: 10, color: '#6b7280', textTransform: 'capitalize' }}>
                      {item.quality_tier}
                    </span>
                  )}
                </div>
                {item.description && (
                  <div style={{ fontSize: 11, color: '#6b7280', lineHeight: 1.4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.description}
                  </div>
                )}
              </div>
            </label>
          ))}
          {filteredItems.length === 0 && (
            <div style={{ textAlign: 'center', color: '#888', fontSize: 13, padding: '24px 0' }}>
              No items match your search.
            </div>
          )}
        </div>

        {/* Footer */}
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
            onClick={handleImport}
            disabled={selected.size === 0 || importing}
            style={{
              padding: '8px 16px', fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
              borderRadius: 6, border: 'none',
              backgroundColor: selected.size > 0 && !importing ? '#191919' : '#e5e7eb',
              color: selected.size > 0 && !importing ? '#fff' : '#9ca3af',
              cursor: selected.size > 0 && !importing ? 'pointer' : 'not-allowed',
              display: 'flex', alignItems: 'center', gap: 6,
            }}
          >
            {importing && <Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite' }} />}
            {importing ? 'Importing...' : `Import ${selected.size} Item${selected.size !== 1 ? 's' : ''}`}
          </button>
        </div>
      </div>
    </div>
  )
}
