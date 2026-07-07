import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { FocusTrap } from 'focus-trap-react'
import type { Library, LibraryItemKind } from '../../types/library'
import { addItem } from '../../api/library'
import { useToast } from '../../contexts/ToastContext'

interface Props {
  libraries: Library[]
  itemId: string
  kind: LibraryItemKind
  onClose: () => void
  onAdded: () => void
}

export function AddToLibraryDialog({ libraries, itemId, kind, onClose, onAdded }: Props) {
  const [selectedLibraryId, setSelectedLibraryId] = useState(libraries[0]?.id ?? '')
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const handleSubmit = async () => {
    if (!selectedLibraryId) return
    setSaving(true)
    try {
      await addItem(selectedLibraryId, { item_id: itemId, kind })
      onAdded()
      onClose()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to add item'
      toast(message, 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black/40" style={{ zIndex: 700 }}>
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6" role="dialog" aria-modal="true" aria-label="Add to Library">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Add to Library</h3>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1 text-gray-500 hover:text-gray-600 rounded">
            <X size={18} />
          </button>
        </div>

        <div>
          <label htmlFor="add-to-library-select" className="block text-sm font-medium text-gray-700 mb-1">Library</label>
          <select
            id="add-to-library-select"
            value={selectedLibraryId}
            onChange={e => setSelectedLibraryId(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
          >
            {libraries.map(lib => (
              <option key={lib.id} value={lib.id}>
                {lib.title} ({lib.scope})
              </option>
            ))}
          </select>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving || !selectedLibraryId}
            className="px-4 py-2 text-sm font-bold text-highlight-text bg-highlight hover:brightness-90 rounded-lg disabled:opacity-50"
          >
            {saving ? 'Adding...' : 'Add'}
          </button>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
