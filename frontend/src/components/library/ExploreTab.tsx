import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Search, ShieldCheck, Beaker,
  ChevronDown, ChevronUp, FolderOpen, Star, X, Plus, ArrowUpDown, Bookmark,
} from 'lucide-react'
import { QualityBadge } from './QualityBadge'
import { AddToLibraryDialog } from './AddToLibraryDialog'
import {
  listVerifiedItems, browseCollections, listFeaturedCollections,
  tryVerifiedItem, listLibraries,
} from '../../api/library'
import { adoptKnowledgeBase } from '../../api/knowledge'
import type { VerifiedCatalogItem, VerifiedCollection, Library, LibraryItemKind } from '../../types/library'
import { useAuth } from '../../hooks/useAuth'

type KindFilter = '' | 'workflow' | 'search_set' | 'knowledge_base'
type SortOption = '' | 'quality' | 'name' | 'validations'
type QualityFilter = '' | 'gold' | 'silver' | 'bronze'

const PAGE_SIZE = 30

function KindLabel({ kind }: { kind: string }) {
  if (kind === 'workflow') return <span className="text-xs px-2 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200">Workflow</span>
  if (kind === 'knowledge_base') return <span className="text-xs px-2 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200">Knowledge Base</span>
  return <span className="text-xs px-2 py-0.5 rounded bg-teal-50 text-teal-700 border border-teal-200">Extraction</span>
}

function TryItPanel({ item }: { item: VerifiedCatalogItem }) {
  const [input, setInput] = useState('')
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleTry = async () => {
    if (!input.trim()) return
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const data = item.kind === 'knowledge_base'
        ? { query: input }
        : { source_text: input }
      const res = await tryVerifiedItem(item.kind, item.item_id, data)
      setResult(res)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mt-3 border-t border-gray-100 pt-3">
      <label className="block text-xs font-medium text-gray-600 mb-1">
        {item.kind === 'knowledge_base' ? 'Test a query' : 'Paste text to extract from'}
      </label>
      <textarea
        value={input}
        onChange={(e) => setInput(e.target.value)}
        rows={3}
        placeholder={item.kind === 'knowledge_base' ? 'Enter a question...' : 'Paste document text...'}
        className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
      />
      <button
        onClick={handleTry}
        disabled={loading || !input.trim()}
        className="mt-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-40"
      >
        {loading ? 'Running...' : 'Try it'}
      </button>
      {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
      {result && (
        <div className="mt-2 bg-gray-50 border border-gray-200 rounded-md p-3 text-xs">
          {item.kind === 'knowledge_base' && Array.isArray((result as Record<string, unknown>).results) ? (
            <div className="space-y-2">
              {((result as Record<string, unknown>).results as { text: string; source_name: string }[]).map((r, i) => (
                <div key={i} className="border-l-2 border-sky-300 pl-2">
                  <p className="text-gray-700">{r.text}</p>
                  {r.source_name && <p className="text-gray-400 mt-0.5">{r.source_name}</p>}
                </div>
              ))}
            </div>
          ) : (
            <pre className="whitespace-pre-wrap text-gray-700 overflow-auto max-h-48">
              {JSON.stringify((result as Record<string, unknown>).extraction_result || result, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

function CatalogCard({
  item,
  onTagClick,
  onAddToLibrary,
  onAdoptKB,
}: {
  item: VerifiedCatalogItem
  onTagClick: (tag: string) => void
  onAddToLibrary: (item: VerifiedCatalogItem) => void
  onAdoptKB?: (kbUuid: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [showTry, setShowTry] = useState(false)
  const canTry = item.kind === 'search_set' || item.kind === 'knowledge_base'

  return (
    <div className="border border-gray-200 rounded-lg bg-white hover:border-gray-300 transition-colors">
      <div className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1.5">
              <ShieldCheck className="h-4 w-4 text-green-500 shrink-0" />
              <span className="text-sm font-semibold text-gray-900 truncate">
                {item.display_name || item.name}
              </span>
            </div>
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <KindLabel kind={item.kind} />
              <QualityBadge tier={item.quality_tier} score={item.quality_score} />
              {item.validation_run_count > 0 && (
                <span className="text-xs text-gray-400">
                  {item.validation_run_count} validation{item.validation_run_count !== 1 ? 's' : ''}
                </span>
              )}
            </div>
            {item.description && (
              <p className="text-xs text-gray-600 line-clamp-2">{item.description}</p>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {item.kind === 'knowledge_base' && onAdoptKB && (
              <button
                onClick={() => item.source_uuid && onAdoptKB(item.source_uuid)}
                className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium text-blue-600 hover:bg-blue-50"
                title="Add to my knowledge bases"
              >
                <Bookmark className="h-3.5 w-3.5" />
                Add to My KBs
              </button>
            )}
            <button
              onClick={() => onAddToLibrary(item)}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium text-gray-600 hover:bg-gray-100"
              title="Add to my library"
            >
              <Plus className="h-3.5 w-3.5" />
              Save
            </button>
            {canTry && (
              <button
                onClick={() => setShowTry(!showTry)}
                className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium text-gray-600 hover:bg-gray-100"
                title="Try it out"
              >
                <Beaker className="h-3.5 w-3.5" />
                Try
              </button>
            )}
            <button
              onClick={() => setExpanded(!expanded)}
              className="p-1 rounded hover:bg-gray-100 text-gray-400"
            >
              {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {item.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {item.tags.map((tag, i) => (
              <button
                key={i}
                onClick={() => onTagClick(tag)}
                className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 hover:bg-gray-200 transition-colors cursor-pointer"
              >
                {tag}
              </button>
            ))}
          </div>
        )}

        {item.kind === 'knowledge_base' && (item.total_sources != null || item.total_chunks != null) && (
          <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
            {item.total_sources != null && (
              <span>{item.total_sources} source{item.total_sources !== 1 ? 's' : ''}</span>
            )}
            {item.total_chunks != null && (
              <span>{item.total_chunks.toLocaleString()} chunks</span>
            )}
          </div>
        )}

        {expanded && item.markdown && (
          <div className="mt-3 border-t border-gray-100 pt-3 text-xs text-gray-600 whitespace-pre-wrap">
            {item.markdown}
          </div>
        )}

        {showTry && <TryItPanel item={item} />}
      </div>
    </div>
  )
}

function CollectionLink({
  collection,
  active,
  onClick,
}: {
  collection: VerifiedCollection
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors flex items-center gap-2 ${
        active
          ? 'bg-gray-900 text-white'
          : 'text-gray-700 hover:bg-gray-100'
      }`}
    >
      <FolderOpen className={`h-3.5 w-3.5 shrink-0 ${active ? 'text-gray-300' : 'text-gray-400'}`} />
      <span className="truncate flex-1">{collection.title}</span>
      {collection.featured && (
        <Star className={`h-3 w-3 shrink-0 fill-current ${active ? 'text-yellow-300' : 'text-yellow-400'}`} />
      )}
      <span className={`text-xs shrink-0 ${active ? 'text-gray-300' : 'text-gray-500'}`}>
        {collection.item_ids.length}
      </span>
    </button>
  )
}

// ── Explore Tab Component ────────────────────────────────────────────────

export function ExploreTab() {
  const { user } = useAuth()

  // Data
  const [items, setItems] = useState<VerifiedCatalogItem[]>([])
  const [total, setTotal] = useState(0)
  const [collections, setCollections] = useState<VerifiedCollection[]>([])
  const [featuredCollections, setFeaturedCollections] = useState<VerifiedCollection[]>([])
  const [libraries, setLibraries] = useState<Library[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)

  // Filters
  const [searchQuery, setSearchQuery] = useState('')
  const [kindFilter, setKindFilter] = useState<KindFilter>('')
  const [qualityFilter, setQualityFilter] = useState<QualityFilter>('')
  const [tagFilter, setTagFilter] = useState('')
  const [sortOption, setSortOption] = useState<SortOption>('')
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null)

  // Add to library dialog
  const [addToLibraryItem, setAddToLibraryItem] = useState<VerifiedCatalogItem | null>(null)

  // Debounced search
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [debouncedSearch, setDebouncedSearch] = useState('')

  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    searchTimerRef.current = setTimeout(() => setDebouncedSearch(searchQuery), 300)
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current) }
  }, [searchQuery])

  // Load collections once
  useEffect(() => {
    browseCollections().then(d => setCollections(d.collections)).catch(() => {})
    listFeaturedCollections().then(d => setFeaturedCollections(d.collections)).catch(() => {})
  }, [])

  // Load user libraries for the "add to library" dialog
  useEffect(() => {
    const teamId = user?.current_team ?? undefined
    listLibraries(teamId).then(setLibraries).catch(() => {})
  }, [user?.current_team])

  // Fetch items when filters change
  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listVerifiedItems({
        kind: kindFilter || undefined,
        search: debouncedSearch || undefined,
        quality_tier: qualityFilter || undefined,
        tag: tagFilter || undefined,
        collection_id: selectedCollectionId || undefined,
        sort: sortOption || undefined,
        skip: 0,
        limit: PAGE_SIZE,
      })
      setItems(data.items)
      setTotal(data.total)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [kindFilter, debouncedSearch, qualityFilter, tagFilter, sortOption, selectedCollectionId])

  useEffect(() => {
    refresh()
  }, [refresh])

  // Load more (pagination)
  const handleLoadMore = async () => {
    setLoadingMore(true)
    try {
      const data = await listVerifiedItems({
        kind: kindFilter || undefined,
        search: debouncedSearch || undefined,
        quality_tier: qualityFilter || undefined,
        tag: tagFilter || undefined,
        collection_id: selectedCollectionId || undefined,
        sort: sortOption || undefined,
        skip: items.length,
        limit: PAGE_SIZE,
      })
      setItems(prev => [...prev, ...data.items])
    } catch {
      // silent
    } finally {
      setLoadingMore(false)
    }
  }

  const hasMore = items.length < total

  const activeCollection = selectedCollectionId
    ? collections.find(c => c.id === selectedCollectionId) ?? null
    : null

  const clearFilters = () => {
    setSearchQuery('')
    setKindFilter('')
    setQualityFilter('')
    setTagFilter('')
    setSortOption('')
    setSelectedCollectionId(null)
  }

  const hasActiveFilters = !!(kindFilter || qualityFilter || tagFilter || sortOption || selectedCollectionId || debouncedSearch)

  const kindFilters: [KindFilter, string][] = [
    ['', 'All'],
    ['workflow', 'Workflows'],
    ['search_set', 'Extractions'],
    ['knowledge_base', 'Knowledge Bases'],
  ]

  const sortOptions: [SortOption, string][] = [
    ['', 'Newest'],
    ['quality', 'Quality'],
    ['name', 'Name'],
    ['validations', 'Most Validated'],
  ]

  return (
    <>
      <div className="flex flex-1 min-h-0">
        {/* ── Sidebar: Collections ── */}
        <div className="w-56 shrink-0 border-r border-gray-200 bg-gray-50/50 overflow-y-auto p-3">
          {/* "All Items" link */}
          <button
            onClick={() => setSelectedCollectionId(null)}
            className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors mb-1 ${
              !selectedCollectionId
                ? 'bg-gray-900 text-white'
                : 'text-gray-700 hover:bg-gray-100'
            }`}
          >
            All Items
            <span className={`ml-1 text-xs ${!selectedCollectionId ? 'text-gray-300' : 'text-gray-500'}`}>
              {total}
            </span>
          </button>

          {/* Featured collections */}
          {featuredCollections.length > 0 && (
            <div className="mt-3 mb-2">
              <div className="flex items-center gap-1 px-3 mb-1">
                <Star className="h-3 w-3 text-yellow-400 fill-current" />
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Featured</span>
              </div>
              {featuredCollections.map(col => (
                <CollectionLink
                  key={col.id}
                  collection={col}
                  active={selectedCollectionId === col.id}
                  onClick={() => setSelectedCollectionId(selectedCollectionId === col.id ? null : col.id)}
                />
              ))}
            </div>
          )}

          {/* All other collections */}
          {collections.filter(c => !featuredCollections.some(f => f.id === c.id)).length > 0 && (
            <div className="mt-3 mb-2">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide px-3">Collections</span>
              <div className="mt-1">
                {collections
                  .filter(c => !featuredCollections.some(f => f.id === c.id))
                  .map(col => (
                    <CollectionLink
                      key={col.id}
                      collection={col}
                      active={selectedCollectionId === col.id}
                      onClick={() => setSelectedCollectionId(selectedCollectionId === col.id ? null : col.id)}
                    />
                  ))}
              </div>
            </div>
          )}
        </div>

        {/* ── Main content ── */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Header */}
          <div className="mb-4">
            {activeCollection ? (
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <FolderOpen className="h-5 w-5 text-gray-400" />
                  <h2 className="text-lg font-bold text-gray-900">{activeCollection.title}</h2>
                  {activeCollection.featured && (
                    <Star className="h-4 w-4 text-yellow-400 fill-current" />
                  )}
                </div>
                {activeCollection.description && (
                  <p className="text-sm text-gray-500 ml-7">{activeCollection.description}</p>
                )}
              </div>
            ) : (
              <div>
                <h2 className="text-lg font-bold text-gray-900">Verified Catalog</h2>
                <p className="text-sm text-gray-500">
                  Browse validated and examiner-approved workflows, extractions, and knowledge bases
                </p>
              </div>
            )}
          </div>

          {/* Search + Filters toolbar */}
          <div className="flex items-center gap-3 mb-4 flex-wrap">
            <div className="relative flex-1 min-w-[200px] max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search items..."
                className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
              />
            </div>

            <div className="flex items-center gap-1.5">
              {kindFilters.map(([val, label]) => (
                <button
                  key={val}
                  onClick={() => setKindFilter(val)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                    kindFilter === val
                      ? 'bg-gray-900 text-white border-gray-900'
                      : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <select
              value={qualityFilter}
              onChange={(e) => setQualityFilter(e.target.value as QualityFilter)}
              className="px-3 py-1.5 text-xs font-medium border border-gray-300 rounded-md bg-white text-gray-600 focus:outline-none focus:ring-1 focus:ring-gray-400"
            >
              <option value="">Any quality</option>
              <option value="gold">Gold</option>
              <option value="silver">Silver</option>
              <option value="bronze">Bronze</option>
            </select>

            <div className="flex items-center gap-1">
              <ArrowUpDown className="h-3.5 w-3.5 text-gray-400" />
              <select
                value={sortOption}
                onChange={(e) => setSortOption(e.target.value as SortOption)}
                className="px-2 py-1.5 text-xs font-medium border border-gray-300 rounded-md bg-white text-gray-600 focus:outline-none focus:ring-1 focus:ring-gray-400"
              >
                {sortOptions.map(([val, label]) => (
                  <option key={val} value={val}>{label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Active filter chips */}
          {hasActiveFilters && (
            <div className="flex items-center gap-2 mb-4 flex-wrap">
              {tagFilter && (
                <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-gray-100 text-gray-700">
                  Tag: {tagFilter}
                  <button onClick={() => setTagFilter('')} className="hover:text-gray-900">
                    <X className="h-3 w-3" />
                  </button>
                </span>
              )}
              {selectedCollectionId && activeCollection && (
                <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-gray-100 text-gray-700">
                  Collection: {activeCollection.title}
                  <button onClick={() => setSelectedCollectionId(null)} className="hover:text-gray-900">
                    <X className="h-3 w-3" />
                  </button>
                </span>
              )}
              <button
                onClick={clearFilters}
                className="text-xs text-gray-500 hover:text-gray-700 underline"
              >
                Clear all
              </button>
              <span className="text-xs text-gray-400 ml-auto">
                {total} result{total !== 1 ? 's' : ''}
              </span>
            </div>
          )}

          {/* Results count */}
          {!hasActiveFilters && !loading && items.length > 0 && (
            <div className="text-xs text-gray-400 mb-3">
              {total} item{total !== 1 ? 's' : ''}
            </div>
          )}

          {/* Results */}
          {loading ? (
            <div className="text-sm text-gray-500 py-12 text-center">Loading...</div>
          ) : items.length === 0 ? (
            <div className="text-center py-16">
              <ShieldCheck className="h-12 w-12 text-gray-300 mx-auto mb-3" />
              <h3 className="text-sm font-medium text-gray-700 mb-1">
                {hasActiveFilters ? 'No matching items' : 'No verified items yet'}
              </h3>
              <p className="text-xs text-gray-500">
                {hasActiveFilters
                  ? 'Try adjusting your filters or search query.'
                  : 'Items submitted by your team and approved by examiners will appear here.'}
              </p>
              {hasActiveFilters && (
                <button
                  onClick={clearFilters}
                  className="mt-3 px-4 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
                >
                  Clear filters
                </button>
              )}
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {items.map(item => (
                  <CatalogCard
                    key={item.id}
                    item={item}
                    onTagClick={(tag) => setTagFilter(tag)}
                    onAddToLibrary={(itm) => setAddToLibraryItem(itm)}
                    onAdoptKB={async (kbUuid) => {
                      try {
                        await adoptKnowledgeBase(kbUuid)
                      } catch { /* ignore duplicates */ }
                    }}
                  />
                ))}
              </div>

              {hasMore && (
                <div className="text-center mt-6">
                  <button
                    onClick={handleLoadMore}
                    disabled={loadingMore}
                    className="px-6 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
                  >
                    {loadingMore ? 'Loading...' : `Load more (${total - items.length} remaining)`}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Add to library dialog */}
      {addToLibraryItem && libraries.length > 0 && (
        <AddToLibraryDialog
          libraries={libraries}
          itemId={addToLibraryItem.item_id}
          kind={addToLibraryItem.kind as LibraryItemKind}
          onClose={() => setAddToLibraryItem(null)}
          onAdded={() => setAddToLibraryItem(null)}
        />
      )}
    </>
  )
}
