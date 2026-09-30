import { usePanelEffect } from '../shared/usePanelEffect'
import { useState } from 'react'
import { X, Search, Loader2 } from 'lucide-react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { importCatalogItems } from '../../api/library'
import type { CatalogPreviewItem } from '../../api/library'
import { useToast } from '../../contexts/ToastContext'

function KindBadge({ kind }: { kind: string }) {
  const isWorkflow = kind === 'workflow'
  return (
    <span
      style={{
        fontSize: 'var(--workspace-font-meta)',
        padding: "1px var(--workspace-space-6)",
        borderRadius: 'var(--workspace-radius-small)',
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
  const { toast } = useToast()

  usePanelEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

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
      await importCatalogItems(file, Array.from(selected))
      onImported()
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : 'Import failed', 'error')
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
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Import from Catalog"
        style={{
          backgroundColor: '#fff', borderRadius: 'var(--workspace-radius-large)', width: 520, maxHeight: '70vh',
          display: 'flex', flexDirection: 'column', boxShadow: 'var(--workspace-shadow-dialog)',
        }}
      >
        {/* Header */}
        <div style={{ padding: "var(--workspace-space-16) var(--workspace-space-20)", borderBottom: "1px solid var(--workspace-border)", display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 'var(--workspace-font-card-title)', fontWeight: 600, color: '#202124' }}>Import from Catalog</span>
          <button type="button" onClick={onClose} aria-label="Close" style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 'var(--workspace-space-4)', color: '#5f6368', display: 'flex' }}>
            <X style={{ width: 18, height: 18 }} />
          </button>
        </div>

        {/* Search */}
        <div style={{ padding: "var(--workspace-space-12) var(--workspace-space-20)", borderBottom: "1px solid var(--workspace-border)" }}>
          <div style={{ position: 'relative' }}>
            <Search style={{ width: 14, height: 14, position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#6b7280' }} />
            <input
              autoFocus
              aria-label="Filter catalog items"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Filter items..."
              style={{
                width: '100%', fontSize: 'var(--workspace-font-control)', fontFamily: 'inherit',
                border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-8) var(--workspace-space-12) var(--workspace-space-8) var(--workspace-space-32)",
                boxSizing: 'border-box',
              }}
            />
          </div>
        </div>

        {/* Item list */}
        <div style={{ flex: 1, overflowY: 'auto', padding: "var(--workspace-space-4) var(--workspace-space-20)", minHeight: 200, maxHeight: 400 }}>
          {/* Select all */}
          <label style={{
            display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', padding: "var(--workspace-space-8) 0",
            borderBottom: "1px solid var(--workspace-border)", cursor: 'pointer', fontSize: 'var(--workspace-font-meta)', color: '#6b7280', fontWeight: 500,
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
                display: 'flex', alignItems: 'flex-start', gap: 'var(--workspace-space-8)', padding: "var(--workspace-space-12) 0",
                borderBottom: '1px solid #f0f0f0', cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={selected.has(item.index)}
                onChange={() => toggle(item.index)}
                style={{ marginTop: 'var(--workspace-space-4)' }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-6)', marginBottom: 'var(--workspace-space-2)' }}>
                  <span style={{ fontSize: 'var(--workspace-font-control)', fontWeight: 500, color: '#202124', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.name}
                  </span>
                  <KindBadge kind={item.item_kind} />
                  {item.quality_tier && (
                    <span style={{ fontSize: 'var(--workspace-font-meta)', color: '#6b7280', textTransform: 'capitalize' }}>
                      {item.quality_tier}
                    </span>
                  )}
                </div>
                {item.description && (
                  <div style={{ fontSize: 'var(--workspace-font-meta)', color: '#6b7280', lineHeight: 1.4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.description}
                  </div>
                )}
              </div>
            </label>
          ))}
          {filteredItems.length === 0 && (
            <div style={{ textAlign: 'center', color: '#888', fontSize: 'var(--workspace-font-control)', padding: "var(--workspace-space-24) 0" }}>
              No items match your search.
            </div>
          )}
        </div>

        {/* Footer */}
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
            onClick={handleImport}
            disabled={selected.size === 0 || importing}
            style={{
              padding: "var(--workspace-space-8) var(--workspace-space-16)", fontSize: 'var(--workspace-font-control)', fontWeight: 700, fontFamily: 'inherit',
              borderRadius: 'var(--workspace-radius-small)', border: 'none',
              backgroundColor: selected.size > 0 && !importing ? 'var(--color-panel-dark)' : '#e5e7eb',
              color: selected.size > 0 && !importing ? '#fff' : '#6b7280',
              cursor: selected.size > 0 && !importing ? 'pointer' : 'not-allowed',
              display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-6)',
            }}
          >
            {importing && <Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite' }} />}
            {importing ? 'Importing...' : `Import ${selected.size} Item${selected.size !== 1 ? 's' : ''}`}
          </button>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
