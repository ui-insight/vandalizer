import { usePanelEffect } from '../shared/usePanelEffect'
import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import type { Library, LibraryItemKind } from '../../types/library'
import { addItem, listItems } from '../../api/library'

interface Props {
  libraries: Library[]
  itemId: string
  itemName?: string
  kind: LibraryItemKind
  onClose: () => void
  onAdded: (library: Library) => void
  onOpen?: () => void
}

export function AddToLibraryDialog({ libraries, itemId, itemName, kind, onClose, onAdded, onOpen }: Props) {
  const [selectedLibraryId, setSelectedLibraryId] = useState(libraries.find(lib => lib.scope === 'personal')?.id ?? libraries[0]?.id ?? '')
  const [saving, setSaving] = useState(false)
  const savingRef = useRef(false)
  const [checking, setChecking] = useState(true)
  const [existing, setExisting] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [checkError, setCheckError] = useState(false)
  const selected = libraries.find(lib => lib.id === selectedLibraryId)

  useEffect(() => {
    let active = true
    setChecking(true); setExisting(false); setSaved(false); setError(null); setCheckError(false)
    if (!selectedLibraryId) { setChecking(false); return }
    listItems(selectedLibraryId, { kind }).then(items => {
      if (active) setExisting(items.some(item => item.item_id === itemId && item.kind === kind))
    }).catch(() => { if (active) setCheckError(true) }).finally(() => { if (active) setChecking(false) })
    return () => { active = false }
  }, [selectedLibraryId, itemId, kind])

  usePanelEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape' && !savingRef.current) onClose() }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const handleSubmit = async () => {
    if (!selected || savingRef.current || checking || existing || saved) return
    savingRef.current = true; setSaving(true); setError(null)
    try {
      await addItem(selected.id, { item_id: itemId, kind })
      setSaved(true)
      onAdded(selected)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save this item. Please try again.')
    } finally {
      savingRef.current = false; setSaving(false)
    }
  }
  const done = existing || saved

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black/40 p-3" style={{ zIndex: 10000 }}>
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
        <div className="bg-white rounded-lg shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto p-6" role="dialog" aria-modal="true" aria-label="Save to Library">
          <div className="flex items-center justify-between mb-4 gap-3">
            <h3 className="text-lg font-semibold text-gray-900">Save to Library</h3>
            <button type="button" disabled={saving} onClick={onClose} aria-label="Close" className="p-1 text-gray-600 rounded disabled:opacity-50"><X size={18} /></button>
          </div>
          {itemName && <p className="text-sm font-medium text-gray-900 mb-2 break-words">{itemName}</p>}
          <p className="text-sm text-gray-600 mb-4">Save a reference to this shared item. Its owner's updates remain available; editing requires your own copy.</p>
          <label htmlFor="add-to-library-select" className="block text-sm font-medium text-gray-700 mb-1">Destination library</label>
          <select id="add-to-library-select" value={selectedLibraryId} disabled={saving || libraries.length === 0} onChange={e => setSelectedLibraryId(e.target.value)} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white">
            {libraries.map(lib => <option key={lib.id} value={lib.id}>{lib.title} ({lib.scope})</option>)}
          </select>
          {libraries.length === 0 && <p role="status" className="mt-3 text-sm text-gray-600">No destination library is available for this account.</p>}
          {checking && selected && <p role="status" className="mt-3 text-sm text-gray-600">Checking this library…</p>}
          {checkError && <p className="mt-3 text-sm text-gray-600">Could not check whether this item is already saved. Saving again keeps the existing reference.</p>}
          {done && <p role="status" className="mt-4 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-800">{saved ? 'Saved to' : 'Already saved in'} {selected?.title}.</p>}
          {error && <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error} Your destination is unchanged. Try saving again.</p>}
          <div className="flex flex-wrap justify-end gap-2 mt-6">
            <button type="button" disabled={saving} onClick={onClose} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg disabled:opacity-50">{done ? 'Done' : 'Cancel'}</button>
            {done ? onOpen && <button type="button" onClick={onOpen} className="px-4 py-2 text-sm font-bold text-highlight-text bg-highlight rounded-lg">Open {kind === 'workflow' ? 'workflow' : 'item'}</button> : <button type="button" onClick={handleSubmit} disabled={saving || checking || !selected} className="px-4 py-2 text-sm font-bold text-highlight-text bg-highlight rounded-lg disabled:opacity-50">{saving ? 'Saving…' : error ? 'Retry save' : 'Save'}</button>}
          </div>
        </div>
      </FocusTrap>
    </div>
  )
}
