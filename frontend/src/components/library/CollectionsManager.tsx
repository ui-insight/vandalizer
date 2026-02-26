import { useCallback, useEffect, useState } from 'react'
import { Plus, Trash2, Pencil, X, FolderOpen, Search } from 'lucide-react'
import {
  listCollections, createCollection, updateCollection, deleteCollection,
  addToCollection, removeFromCollection, listVerifiedItems,
} from '../../api/library'
import type { VerifiedCollection, VerifiedCatalogItem } from '../../types/library'

export function CollectionsManager() {
  const [collections, setCollections] = useState<VerifiedCollection[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [creating, setCreating] = useState(false)

  // Edit state
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editDescription, setEditDescription] = useState('')

  // Add item state
  const [showAddItem, setShowAddItem] = useState(false)
  const [verifiedItems, setVerifiedItems] = useState<VerifiedCatalogItem[]>([])
  const [addSearch, setAddSearch] = useState('')
  const [loadingItems, setLoadingItems] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listCollections()
      setCollections(data.collections)
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const selected = collections.find(c => c.id === selectedId) || null

  const handleCreate = async () => {
    if (!newTitle.trim()) return
    setCreating(true)
    try {
      await createCollection({ title: newTitle.trim(), description: newDescription.trim() || undefined })
      setNewTitle('')
      setNewDescription('')
      setShowCreate(false)
      refresh()
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (id: string) => {
    const col = collections.find(c => c.id === id)
    if (!col || !confirm(`Delete collection "${col.title}"?`)) return
    await deleteCollection(id)
    if (selectedId === id) setSelectedId(null)
    refresh()
  }

  const handleSaveEdit = async () => {
    if (!editingId || !editTitle.trim()) return
    await updateCollection(editingId, {
      title: editTitle.trim(),
      description: editDescription.trim() || undefined,
    })
    setEditingId(null)
    refresh()
  }

  const startEdit = (col: VerifiedCollection) => {
    setEditingId(col.id)
    setEditTitle(col.title)
    setEditDescription(col.description || '')
  }

  const handleOpenAddItem = async () => {
    setShowAddItem(true)
    setLoadingItems(true)
    try {
      const data = await listVerifiedItems()
      setVerifiedItems(data.items)
    } finally {
      setLoadingItems(false)
    }
  }

  const handleAddItem = async (itemId: string) => {
    if (!selectedId) return
    await addToCollection(selectedId, itemId)
    refresh()
  }

  const handleRemoveItem = async (itemId: string) => {
    if (!selectedId) return
    await removeFromCollection(selectedId, itemId)
    refresh()
  }

  const filteredVerified = addSearch
    ? verifiedItems.filter(v =>
        v.name.toLowerCase().includes(addSearch.toLowerCase()) ||
        (v.display_name || '').toLowerCase().includes(addSearch.toLowerCase())
      )
    : verifiedItems

  // Items already in the selected collection
  const collectionItemIds = new Set(selected?.item_ids || [])

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm text-gray-500">{collections.length} collection{collections.length !== 1 ? 's' : ''}</div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-gray-900 text-white rounded-md hover:bg-gray-800"
        >
          <Plus className="h-4 w-4" /> New Collection
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="border border-gray-200 rounded-lg p-4 bg-white mb-4">
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Title</label>
              <input
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="Collection title..."
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
              <textarea
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                placeholder="Optional description..."
                rows={2}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleCreate}
                disabled={creating || !newTitle.trim()}
                className="px-4 py-2 text-sm font-medium text-white bg-gray-900 rounded-md hover:bg-gray-800 disabled:opacity-50"
              >
                {creating ? 'Creating...' : 'Create'}
              </button>
              <button
                onClick={() => { setShowCreate(false); setNewTitle(''); setNewDescription('') }}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-sm text-gray-500 py-8 text-center">Loading...</div>
      ) : collections.length === 0 ? (
        <div className="text-sm text-gray-500 py-12 text-center">
          No collections yet. Create one to get started.
        </div>
      ) : (
        <div className="space-y-2">
          {collections.map((col) => {
            const isSelected = selectedId === col.id
            const isEditing = editingId === col.id

            return (
              <div key={col.id} className="border border-gray-200 rounded-lg bg-white">
                <div
                  className={`p-4 cursor-pointer hover:bg-gray-50 transition-colors ${isSelected ? 'bg-gray-50' : ''}`}
                  onClick={() => setSelectedId(isSelected ? null : col.id)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      {isEditing ? (
                        <div className="space-y-2" onClick={e => e.stopPropagation()}>
                          <input
                            type="text"
                            value={editTitle}
                            onChange={(e) => setEditTitle(e.target.value)}
                            className="w-full px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-gray-400"
                          />
                          <textarea
                            value={editDescription}
                            onChange={(e) => setEditDescription(e.target.value)}
                            rows={2}
                            className="w-full px-2 py-1 text-sm border border-gray-300 rounded resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
                          />
                          <div className="flex gap-1">
                            <button
                              onClick={handleSaveEdit}
                              className="px-3 py-1 text-xs font-medium bg-gray-900 text-white rounded hover:bg-gray-800"
                            >
                              Save
                            </button>
                            <button
                              onClick={() => setEditingId(null)}
                              className="px-3 py-1 text-xs font-medium bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div className="flex items-center gap-2 mb-1">
                            <FolderOpen className="h-4 w-4 text-gray-400 shrink-0" />
                            <span className="text-sm font-semibold text-gray-900">{col.title}</span>
                            <span className="text-xs text-gray-500">
                              {col.item_ids.length} item{col.item_ids.length !== 1 ? 's' : ''}
                            </span>
                          </div>
                          {col.description && (
                            <p className="text-xs text-gray-600 ml-6 line-clamp-2">{col.description}</p>
                          )}
                        </>
                      )}
                    </div>
                    {!isEditing && (
                      <div className="flex items-center gap-1 shrink-0" onClick={e => e.stopPropagation()}>
                        <button
                          onClick={() => startEdit(col)}
                          className="p-1.5 rounded hover:bg-gray-100 text-gray-500"
                          title="Edit"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(col.id)}
                          className="p-1.5 rounded hover:bg-red-50 text-red-500"
                          title="Delete"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                {/* Expanded: items in collection */}
                {isSelected && (
                  <div className="border-t border-gray-100 p-4 bg-gray-50/50">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Items</span>
                      <button
                        onClick={handleOpenAddItem}
                        className="flex items-center gap-1 px-2 py-1 text-xs font-medium bg-white border border-gray-300 rounded hover:bg-gray-50"
                      >
                        <Plus className="h-3 w-3" /> Add Item
                      </button>
                    </div>
                    {col.item_ids.length === 0 ? (
                      <div className="text-xs text-gray-500 py-4 text-center">No items in this collection.</div>
                    ) : (
                      <div className="space-y-1">
                        {col.item_ids.map((itemId) => (
                          <div key={itemId} className="flex items-center justify-between px-3 py-2 bg-white rounded border border-gray-200">
                            <span className="text-xs font-mono text-gray-700 truncate">{itemId}</span>
                            <button
                              onClick={() => handleRemoveItem(itemId)}
                              className="p-1 rounded hover:bg-red-50 text-red-500 shrink-0"
                              title="Remove"
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Add item modal inline */}
                    {showAddItem && (
                      <div className="mt-3 border border-gray-200 rounded-lg p-3 bg-white">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-xs font-semibold text-gray-700">Add Verified Item</span>
                          <button onClick={() => { setShowAddItem(false); setAddSearch('') }} className="p-1 rounded hover:bg-gray-100 text-gray-500">
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                        <div className="relative mb-2">
                          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
                          <input
                            type="text"
                            value={addSearch}
                            onChange={(e) => setAddSearch(e.target.value)}
                            placeholder="Search items..."
                            className="w-full pl-8 pr-3 py-1.5 text-xs border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-gray-400"
                          />
                        </div>
                        {loadingItems ? (
                          <div className="text-xs text-gray-500 py-3 text-center">Loading...</div>
                        ) : (
                          <div className="max-h-40 overflow-y-auto space-y-1">
                            {filteredVerified.filter(v => !collectionItemIds.has(v.item_id)).map((v) => (
                              <button
                                key={v.id}
                                onClick={() => handleAddItem(v.item_id)}
                                className="w-full flex items-center justify-between px-2 py-1.5 text-xs rounded hover:bg-gray-50 text-left"
                              >
                                <span className="truncate">{v.display_name || v.name}</span>
                                <span className={`ml-2 text-xs px-1.5 py-0.5 rounded shrink-0 ${
                                  v.kind === 'workflow' ? 'bg-purple-50 text-purple-700' : 'bg-teal-50 text-teal-700'
                                }`}>
                                  {v.kind === 'workflow' ? 'WF' : 'EX'}
                                </span>
                              </button>
                            ))}
                            {filteredVerified.filter(v => !collectionItemIds.has(v.item_id)).length === 0 && (
                              <div className="text-xs text-gray-500 py-2 text-center">No items available to add.</div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
