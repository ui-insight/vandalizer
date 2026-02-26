import { useState } from 'react'
import { Search } from 'lucide-react'
import { useLibraryItems } from '../../hooks/useLibrary'
import { cloneToPersonal, shareToTeam } from '../../api/library'
import type { Library } from '../../types/library'
import type { LibraryItem } from '../../types/library'
import { LibraryItemRow } from './LibraryItemRow'
import { LibraryItemDetails } from './LibraryItemDetails'

interface Props {
  library: Library
  teamId?: string
}

export function LibraryItemsPanel({ library, teamId }: Props) {
  const [kindFilter, setKindFilter] = useState<string | undefined>()
  const [search, setSearch] = useState('')
  const [selectedItem, setSelectedItem] = useState<LibraryItem | null>(null)
  const { items, loading, refresh, update, remove } = useLibraryItems(library.id, {
    kind: kindFilter,
    search: search || undefined,
  })

  const handlePin = async (itemId: string, pinned: boolean) => {
    await update(itemId, { pinned })
  }

  const handleFavorite = async (itemId: string, favorited: boolean) => {
    await update(itemId, { favorited })
  }

  const handleClone = async (itemId: string) => {
    await cloneToPersonal(itemId)
    refresh()
  }

  const handleShare = async (itemId: string) => {
    if (!teamId) return
    await shareToTeam(itemId, teamId)
    refresh()
  }

  const handleRemove = async (itemId: string) => {
    if (selectedItem?.id === itemId) {
      setSelectedItem(null)
    }
    await remove(itemId)
  }

  const handleOpen = (item: LibraryItem) => {
    setSelectedItem(item)
  }

  // Sort: pinned first, then favorited, then by date
  const sorted = [...items].sort((a, b) => {
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
    if (a.favorited !== b.favorited) return a.favorited ? -1 : 1
    return 0
  })

  return (
    <div className="flex h-full">
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">{library.title}</h2>
          <span className="text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-500">{library.scope}</span>
        </div>

        {library.description && (
          <p className="text-sm text-gray-500 mb-4">{library.description}</p>
        )}

        <div className="flex items-center gap-2 mb-4">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search items..."
              className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
            />
          </div>
          <select
            value={kindFilter ?? ''}
            onChange={e => setKindFilter(e.target.value || undefined)}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
          >
            <option value="">All types</option>
            <option value="workflow">Workflows</option>
            <option value="search_set">Search Sets</option>
          </select>
        </div>

        {loading ? (
          <div className="text-sm text-gray-500">Loading...</div>
        ) : sorted.length === 0 ? (
          <div className="text-sm text-gray-500 text-center py-12">
            No items in this library yet.
          </div>
        ) : (
          <div className="grid gap-2">
            {sorted.map(item => (
              <LibraryItemRow
                key={item.id}
                item={item}
                scope={library.scope === 'team' ? 'team' : 'mine'}
                onPin={handlePin}
                onFavorite={handleFavorite}
                onClone={handleClone}
                onShare={handleShare}
                onRemove={handleRemove}
                onOpen={handleOpen}
              />
            ))}
          </div>
        )}
      </div>

      {selectedItem && (
        <LibraryItemDetails
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          onRemove={handleRemove}
        />
      )}
    </div>
  )
}
