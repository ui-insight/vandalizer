import { useCallback, useEffect, useState } from 'react'
import { Search, ShieldCheck, X, Pencil, ShieldOff, Tag } from 'lucide-react'
import { listVerifiedItems, updateItemMetadata, unverifyItem, listGroups } from '../../api/library'
import type { VerifiedCatalogItem, Group } from '../../types/library'

type KindFilter = '' | 'workflow' | 'search_set'

function KindBadge({ kind }: { kind: string }) {
  const isWorkflow = kind === 'workflow'
  return (
    <span className={`text-xs px-2 py-0.5 rounded border ${
      isWorkflow
        ? 'bg-purple-50 text-purple-700 border-purple-200'
        : 'bg-teal-50 text-teal-700 border-teal-200'
    }`}>
      {isWorkflow ? 'Workflow' : 'Extraction'}
    </span>
  )
}

interface MetadataModalProps {
  item: VerifiedCatalogItem
  onClose: () => void
  onSaved: () => void
}

function MetadataModal({ item, onClose, onSaved }: MetadataModalProps) {
  const [displayName, setDisplayName] = useState(item.display_name || '')
  const [description, setDescription] = useState(item.description || '')
  const [markdown, setMarkdown] = useState(item.markdown || '')
  const [selectedGroupIds, setSelectedGroupIds] = useState<string[]>(item.group_ids || [])
  const [allGroups, setAllGroups] = useState<Group[]>([])
  const [saving, setSaving] = useState(false)
  const [showPreview, setShowPreview] = useState(false)

  useEffect(() => {
    listGroups().then(data => setAllGroups(data.groups)).catch(() => {})
  }, [])

  const toggleGroup = (uuid: string) => {
    setSelectedGroupIds(prev =>
      prev.includes(uuid) ? prev.filter(id => id !== uuid) : [...prev, uuid]
    )
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await updateItemMetadata(item.kind, item.item_id, {
        display_name: displayName || undefined,
        description: description || undefined,
        markdown: markdown || undefined,
        group_ids: selectedGroupIds,
      })
      onSaved()
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <h3 className="text-base font-semibold text-gray-900">Edit Metadata</h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100 text-gray-500">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          <div className="text-xs text-gray-500 flex items-center gap-2">
            <KindBadge kind={item.kind} />
            <span className="font-mono">{item.name}</span>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder={item.name}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Brief description..."
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
            />
          </div>
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-sm font-medium text-gray-700">Documentation (Markdown)</label>
              <button
                onClick={() => setShowPreview(!showPreview)}
                className="text-xs text-gray-500 hover:text-gray-700"
              >
                {showPreview ? 'Edit' : 'Preview'}
              </button>
            </div>
            {showPreview ? (
              <div className="border border-gray-300 rounded-md p-3 min-h-[120px] text-sm text-gray-700 prose prose-sm max-w-none whitespace-pre-wrap">
                {markdown || <span className="text-gray-400 italic">No documentation</span>}
              </div>
            ) : (
              <textarea
                value={markdown}
                onChange={(e) => setMarkdown(e.target.value)}
                rows={6}
                placeholder="Detailed documentation in markdown..."
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-y font-mono focus:outline-none focus:ring-1 focus:ring-gray-400"
              />
            )}
          </div>
          {allGroups.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Groups (visibility restriction)</label>
              <p className="text-xs text-gray-500 mb-2">
                No groups selected = visible to everyone. Selected groups restrict visibility to group members only.
              </p>
              <div className="space-y-1.5 max-h-40 overflow-y-auto">
                {allGroups.map(group => (
                  <label key={group.uuid} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-gray-50 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedGroupIds.includes(group.uuid)}
                      onChange={() => toggleGroup(group.uuid)}
                      className="rounded border-gray-300"
                    />
                    <span className="text-sm text-gray-700">{group.name}</span>
                    {group.description && (
                      <span className="text-xs text-gray-400 truncate">{group.description}</span>
                    )}
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-gray-200">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 text-sm font-medium text-white bg-gray-900 rounded-md hover:bg-gray-800 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

export function VerifiedCatalog() {
  const [items, setItems] = useState<VerifiedCatalogItem[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [kindFilter, setKindFilter] = useState<KindFilter>('')
  const [editingItem, setEditingItem] = useState<VerifiedCatalogItem | null>(null)
  const [groupMap, setGroupMap] = useState<Record<string, string>>({})

  // Load groups for displaying badges
  useEffect(() => {
    listGroups()
      .then(data => {
        const map: Record<string, string> = {}
        for (const g of data.groups) map[g.uuid] = g.name
        setGroupMap(map)
      })
      .catch(() => {})
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listVerifiedItems(
        kindFilter || undefined,
        searchQuery || undefined,
      )
      setItems(data.items)
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }, [kindFilter, searchQuery])

  useEffect(() => {
    refresh()
  }, [refresh])

  const handleUnverify = async (item: VerifiedCatalogItem) => {
    if (!confirm(`Remove verified status from "${item.display_name || item.name}"?`)) return
    await unverifyItem(item.kind, item.item_id)
    refresh()
  }

  return (
    <div>
      {/* Search + filter */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search verified items..."
            className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
          />
        </div>
        <div className="flex items-center gap-2">
          {([['', 'All'], ['workflow', 'Workflows'], ['search_set', 'Extractions']] as [KindFilter, string][]).map(([val, label]) => (
            <button
              key={val}
              onClick={() => setKindFilter(val)}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                kindFilter === val
                  ? 'bg-gray-900 text-white border-gray-900'
                  : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="text-sm text-gray-500 py-8 text-center">Loading...</div>
      ) : items.length === 0 ? (
        <div className="text-sm text-gray-500 py-12 text-center">
          No verified items found.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {items.map((item) => (
            <div
              key={item.id}
              className="border border-gray-200 rounded-lg p-4 bg-white hover:border-gray-300 transition-colors"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <ShieldCheck className="h-4 w-4 text-green-500 shrink-0" />
                    <span className="text-sm font-semibold text-gray-900 truncate">
                      {item.display_name || item.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mb-2">
                    <KindBadge kind={item.kind} />
                    {item.created_at && (
                      <span className="text-xs text-gray-500">
                        {new Date(item.created_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                  {item.description && (
                    <p className="text-xs text-gray-600 line-clamp-2">{item.description}</p>
                  )}
                  {item.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {item.tags.map((tag, i) => (
                        <span key={i} className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                  {item.group_ids?.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {item.group_ids.map(gid => (
                        <span key={gid} className="text-xs px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200 flex items-center gap-1">
                          <Tag className="h-3 w-3" />
                          {groupMap[gid] || gid}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => setEditingItem(item)}
                    className="p-1.5 rounded hover:bg-gray-100 text-gray-500"
                    title="Edit Metadata"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => handleUnverify(item)}
                    className="p-1.5 rounded hover:bg-red-50 text-red-500"
                    title="Unverify"
                  >
                    <ShieldOff className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {editingItem && (
        <MetadataModal
          item={editingItem}
          onClose={() => setEditingItem(null)}
          onSaved={refresh}
        />
      )}
    </div>
  )
}
