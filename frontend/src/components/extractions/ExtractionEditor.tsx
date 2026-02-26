import { useState } from 'react'
import { Plus, Trash2, X } from 'lucide-react'
import { useSearchSetItems } from '../../hooks/useExtractions'
import type { SearchSet } from '../../types/workflow'

interface Props {
  searchSet: SearchSet
  onClose: () => void
}

export function ExtractionEditor({ searchSet, onClose }: Props) {
  const { items, loading, add, remove } = useSearchSetItems(searchSet.uuid)
  const [newPhrase, setNewPhrase] = useState('')

  const handleAdd = async () => {
    if (!newPhrase.trim()) return
    await add(newPhrase.trim())
    setNewPhrase('')
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-medium text-gray-900">{searchSet.title}</h3>
        <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600">
          <X size={18} />
        </button>
      </div>

      {/* Add item */}
      <div className="flex gap-2 mb-3">
        <input
          type="text"
          value={newPhrase}
          onChange={e => setNewPhrase(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleAdd()}
          placeholder="Add extraction field..."
          className="flex-1 px-2 py-1.5 text-sm border border-gray-300 rounded"
        />
        <button
          onClick={handleAdd}
          disabled={!newPhrase.trim()}
          className="flex items-center gap-1 px-3 py-1.5 bg-highlight text-highlight-text rounded text-sm font-bold hover:brightness-90 disabled:opacity-50"
        >
          <Plus size={14} />
          Add
        </button>
      </div>

      {/* Items list */}
      {loading ? (
        <div className="text-sm text-gray-500">Loading...</div>
      ) : items.length === 0 ? (
        <div className="text-sm text-gray-500">No extraction fields yet.</div>
      ) : (
        <ul className="space-y-1">
          {items.map(item => (
            <li key={item.id} className="flex items-center justify-between py-1.5 px-2 bg-gray-50 rounded text-sm">
              <span className="text-gray-800">{item.searchphrase}</span>
              <button
                onClick={() => remove(item.id)}
                className="p-1 text-gray-400 hover:text-red-500"
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
