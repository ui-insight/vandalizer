import { useState } from 'react'
import { X } from 'lucide-react'
import type { Library, LibraryItemKind } from '../../types/library'
import { addItem } from '../../api/library'

interface Props {
  libraries: Library[]
  itemId: string
  kind: LibraryItemKind
  onClose: () => void
  onAdded: () => void
}

export function AddToLibraryDialog({ libraries, itemId, kind, onClose, onAdded }: Props) {
  const [selectedLibraryId, setSelectedLibraryId] = useState(libraries[0]?.id ?? '')
  const [note, setNote] = useState('')
  const [tags, setTags] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSubmit = async () => {
    if (!selectedLibraryId) return
    setSaving(true)
    try {
      await addItem(selectedLibraryId, {
        item_id: itemId,
        kind,
        note: note || undefined,
        tags: tags ? tags.split(',').map(t => t.trim()).filter(Boolean) : undefined,
      })
      onAdded()
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Add to Library</h3>
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600 rounded">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Library</label>
            <select
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

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Note (optional)</label>
            <input
              type="text"
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="Add a note..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Tags (comma separated)</label>
            <input
              type="text"
              value={tags}
              onChange={e => setTags(e.target.value)}
              placeholder="tag1, tag2, ..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
            />
          </div>
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
    </div>
  )
}
