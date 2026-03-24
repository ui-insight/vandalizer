import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import {
  Search, ShieldCheck, BookOpen, Workflow, FileSearch,
  FolderOpen, Star, X, Plus, ArrowUpDown,
  Bookmark, ArrowLeft, Loader2, Tag, Sparkles, ExternalLink,
} from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { QualityBadge } from './QualityBadge'
import { AddToLibraryDialog } from './AddToLibraryDialog'
import {
  listVerifiedItems, browseCollections, listFeaturedCollections,
  listLibraries,
} from '../../api/library'
import { adoptKnowledgeBase } from '../../api/knowledge'
import type { VerifiedCatalogItem, VerifiedCollection, Library, LibraryItemKind } from '../../types/library'
import { useAuth } from '../../hooks/useAuth'
import { useToast } from '../../contexts/ToastContext'

marked.setOptions({ breaks: true, gfm: true })

type KindFilter = '' | 'workflow' | 'search_set' | 'knowledge_base'
type SortOption = '' | 'quality' | 'name' | 'validations'
type QualityFilter = '' | 'gold' | 'silver' | 'bronze'

const PAGE_SIZE = 30

// ---------------------------------------------------------------------------
// Markdown renderer
// ---------------------------------------------------------------------------

function Markdown({ text }: { text: string }) {
  const html = useMemo(
    () => DOMPurify.sanitize(marked.parse(text) as string),
    [text],
  )
  return (
    <div
      className="chat-markdown text-sm text-gray-700"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

// ---------------------------------------------------------------------------
// Kind helpers
// ---------------------------------------------------------------------------

const KIND_CONFIG = {
  workflow: {
    label: 'Workflow',
    icon: Workflow,
    bg: 'bg-purple-50', text: 'text-purple-700', border: 'border-purple-200',
    heroBg: 'from-purple-500 to-purple-700',
  },
  search_set: {
    label: 'Extraction',
    icon: FileSearch,
    bg: 'bg-teal-50', text: 'text-teal-700', border: 'border-teal-200',
    heroBg: 'from-teal-500 to-teal-700',
  },
  knowledge_base: {
    label: 'Knowledge Base',
    icon: BookOpen,
    bg: 'bg-sky-50', text: 'text-sky-700', border: 'border-sky-200',
    heroBg: 'from-sky-500 to-sky-700',
  },
} as const

function KindBadge({ kind }: { kind: string }) {
  const c = KIND_CONFIG[kind as keyof typeof KIND_CONFIG]
  if (!c) return null
  const Icon = c.icon
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded ${c.bg} ${c.text} border ${c.border}`}>
      <Icon className="h-3 w-3" />
      {c.label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Quality tier styling
// ---------------------------------------------------------------------------

const TIER_STYLES = {
  gold: { ring: 'ring-amber-300', glow: 'shadow-amber-100', accent: 'text-amber-600', bg: 'bg-amber-50' },
  silver: { ring: 'ring-gray-300', glow: 'shadow-gray-100', accent: 'text-gray-500', bg: 'bg-gray-50' },
  bronze: { ring: 'ring-orange-200', glow: 'shadow-orange-50', accent: 'text-orange-600', bg: 'bg-orange-50' },
} as const

// ---------------------------------------------------------------------------
// Item Detail Modal
// ---------------------------------------------------------------------------

export function ItemDetailModal({
  item,
  onClose,
  onAddToLibrary,
  onAdoptKB,
  onTryIt,
}: {
  item: VerifiedCatalogItem
  onClose: () => void
  onAddToLibrary: (item: VerifiedCatalogItem) => void
  onAdoptKB?: (kbUuid: string) => void
  onTryIt?: (item: VerifiedCatalogItem) => void
}) {
  const tierStyle = TIER_STYLES[(item.quality_tier || '') as keyof typeof TIER_STYLES]
  const kindConf = KIND_CONFIG[item.kind as keyof typeof KIND_CONFIG]

  return (
    <div className="fixed inset-0 z-[9990] flex items-start justify-center pt-[5vh] bg-black/40" onClick={onClose}>
      <div
        className="w-full max-w-2xl max-h-[85vh] overflow-y-auto bg-white rounded-2xl shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header bar */}
        <div className={`px-6 py-5 bg-gradient-to-r ${kindConf?.heroBg || 'from-gray-600 to-gray-800'} text-white rounded-t-2xl`}>
          <div className="flex items-start justify-between">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-2">
                <ShieldCheck className="h-5 w-5 text-white/80" />
                <span className="text-xs font-medium text-white/70 uppercase tracking-wide">
                  Verified {kindConf?.label || item.kind}
                </span>
              </div>
              <h2 className="text-xl font-bold">{item.display_name || item.name}</h2>
              {item.description && (
                <p className="mt-1.5 text-sm text-white/80">{item.description}</p>
              )}
            </div>
            <button onClick={onClose} className="p-1 rounded-lg hover:bg-white/10 text-white/60 hover:text-white">
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Stats row */}
          <div className="flex items-center gap-4 mt-4 text-sm">
            <QualityBadge tier={item.quality_tier} score={item.quality_score} />
            {item.validation_run_count > 0 && (
              <span className="text-white/70">{item.validation_run_count} validation{item.validation_run_count !== 1 ? 's' : ''}</span>
            )}
            {item.kind === 'knowledge_base' && item.total_sources != null && (
              <span className="text-white/70">{item.total_sources} source{item.total_sources !== 1 ? 's' : ''}</span>
            )}
            {item.kind === 'knowledge_base' && item.total_chunks != null && (
              <span className="text-white/70">{item.total_chunks.toLocaleString()} chunks</span>
            )}
          </div>
        </div>

        {/* Body */}
        <div className="px-6 py-5">
          {/* Tags */}
          {item.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-5">
              {item.tags.map((tag, i) => (
                <span key={i} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-gray-100 text-gray-600">
                  <Tag className="h-2.5 w-2.5" />
                  {tag}
                </span>
              ))}
            </div>
          )}

          {/* Markdown documentation */}
          {item.markdown && (
            <div className={`rounded-xl p-5 mb-5 ${tierStyle?.bg || 'bg-gray-50'} border border-gray-100`}>
              <Markdown text={item.markdown} />
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2 pt-2 border-t border-gray-100">
            {item.kind === 'knowledge_base' && onAdoptKB && item.source_uuid && (
              <button
                onClick={() => onAdoptKB(item.source_uuid!)}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 transition-colors"
              >
                <Bookmark className="h-4 w-4" />
                Add to My Knowledge Bases
              </button>
            )}
            {item.kind === 'knowledge_base' && item.source_uuid && onTryIt && (
              <button
                onClick={() => onTryIt(item)}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 transition-colors"
              >
                <ExternalLink className="h-4 w-4" />
                Open in Chat
              </button>
            )}
            {item.kind !== 'knowledge_base' && (
              <button
                onClick={() => onAddToLibrary(item)}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 transition-colors"
              >
                <Plus className="h-4 w-4" />
                Save to Library
              </button>
            )}
            {(item.kind === 'search_set' || item.kind === 'workflow') && item.source_uuid && onTryIt && (
              <button
                onClick={() => onTryIt(item)}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 transition-colors"
              >
                <ExternalLink className="h-4 w-4" />
                Open
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Featured Collection Card
// ---------------------------------------------------------------------------

function FeaturedCollectionCard({
  collection,
  onClick,
}: {
  collection: VerifiedCollection
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className="group flex flex-col rounded-xl border border-gray-200 bg-white p-5 text-left hover:border-gray-300 hover:shadow-md transition-all"
    >
      <div className="flex items-start gap-2 mb-2">
        <div className="flex items-center justify-center h-8 w-8 rounded-lg bg-yellow-50 text-yellow-600 shrink-0">
          <Star className="h-4 w-4 fill-current" />
        </div>
        <h3 className="text-sm font-bold text-gray-900 group-hover:text-blue-700 transition-colors line-clamp-2 flex-1 min-w-0">
          {collection.title}
        </h3>
      </div>
      {collection.description && (
        <p className="text-xs text-gray-500 line-clamp-3 mb-3">{collection.description}</p>
      )}
      <span className="mt-auto text-xs font-medium text-gray-400">
        {collection.item_ids.length} item{collection.item_ids.length !== 1 ? 's' : ''}
      </span>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Catalog Card (compact, in grid)
// ---------------------------------------------------------------------------

function CatalogCard({
  item,
  onTagClick,
  onClick,
}: {
  item: VerifiedCatalogItem
  onTagClick: (tag: string) => void
  onClick: () => void
}) {
  const tierStyle = TIER_STYLES[(item.quality_tier || '') as keyof typeof TIER_STYLES]

  return (
    <button
      onClick={onClick}
      className={`group flex flex-col rounded-xl border bg-white p-4 text-left transition-all hover:shadow-md ${
        tierStyle ? `ring-1 ${tierStyle.ring} hover:${tierStyle.glow}` : 'border-gray-200 hover:border-gray-300'
      }`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-1.5 mb-1">
            <ShieldCheck className={`h-3.5 w-3.5 shrink-0 mt-0.5 ${
              item.quality_tier === 'gold' ? 'text-amber-500' : item.quality_tier === 'silver' ? 'text-gray-400' : 'text-green-500'
            }`} />
            <span className="text-sm font-semibold text-gray-900 line-clamp-2 flex-1 min-w-0 group-hover:text-blue-700 transition-colors">
              {item.display_name || item.name}
            </span>
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            <KindBadge kind={item.kind} />
            <QualityBadge tier={item.quality_tier} score={item.quality_score} />
            {item.validation_run_count > 0 && (
              <span className="text-[10px] text-gray-400">
                {item.validation_run_count} val{item.validation_run_count !== 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
      </div>

      {item.description && (
        <p className="text-xs text-gray-600 line-clamp-3 mb-2">{item.description}</p>
      )}

      {item.kind === 'knowledge_base' && (item.total_sources != null || item.total_chunks != null) && (
        <div className="flex items-center gap-3 text-[11px] text-gray-400 mb-2">
          {item.total_sources != null && <span>{item.total_sources} source{item.total_sources !== 1 ? 's' : ''}</span>}
          {item.total_chunks != null && <span>{item.total_chunks.toLocaleString()} chunks</span>}
        </div>
      )}

      {item.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-auto pt-2">
          {item.tags.slice(0, 4).map((tag, i) => (
            <span
              key={i}
              onClick={(e) => { e.stopPropagation(); onTagClick(tag) }}
              className="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-500 hover:bg-gray-200 hover:text-gray-700 cursor-pointer transition-colors"
            >
              {tag}
            </span>
          ))}
          {item.tags.length > 4 && (
            <span className="text-[10px] text-gray-400">+{item.tags.length - 4}</span>
          )}
        </div>
      )}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Collection sidebar link
// ---------------------------------------------------------------------------

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
      className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors flex items-start gap-2 ${
        active
          ? 'bg-gray-900 text-white'
          : 'text-gray-700 hover:bg-gray-100'
      }`}
    >
      <FolderOpen className={`h-3.5 w-3.5 shrink-0 mt-0.5 ${active ? 'text-gray-300' : 'text-gray-400'}`} />
      <span className="line-clamp-2 flex-1 min-w-0 text-left leading-snug">{collection.title}</span>
      {collection.featured && (
        <Star className={`h-3 w-3 shrink-0 fill-current ${active ? 'text-yellow-300' : 'text-yellow-400'}`} />
      )}
      <span className={`text-xs shrink-0 ${active ? 'text-gray-300' : 'text-gray-500'}`}>
        {collection.item_ids.length}
      </span>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Main ExploreTab
// ---------------------------------------------------------------------------

export function ExploreTab() {
  const { user } = useAuth()
  const { toast } = useToast()

  // Data
  const [items, setItems] = useState<VerifiedCatalogItem[]>([])
  const [total, setTotal] = useState(0)
  const [collections, setCollections] = useState<VerifiedCollection[]>([])
  const [featuredCollections, setFeaturedCollections] = useState<VerifiedCollection[]>([])
  const [libraries, setLibraries] = useState<Library[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [searchQuery, setSearchQuery] = useState('')
  const [kindFilter, setKindFilter] = useState<KindFilter>('')
  const [qualityFilter, setQualityFilter] = useState<QualityFilter>('')
  const [tagFilter, setTagFilter] = useState('')
  const [sortOption, setSortOption] = useState<SortOption>('')
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null)

  // Detail + dialogs
  const [detailItem, setDetailItem] = useState<VerifiedCatalogItem | null>(null)
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
    browseCollections()
      .then(d => setCollections(d.collections))
      .catch(() => setError('Failed to load collections'))
    listFeaturedCollections()
      .then(d => setFeaturedCollections(d.collections))
      .catch(() => {})
  }, [])

  // Load user libraries
  useEffect(() => {
    const teamId = user?.current_team ?? undefined
    listLibraries(teamId).then(setLibraries).catch(() => {})
  }, [user?.current_team])

  // Fetch items when filters change
  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
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
      setError('Failed to load catalog items. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [kindFilter, debouncedSearch, qualityFilter, tagFilter, sortOption, selectedCollectionId])

  useEffect(() => { refresh() }, [refresh])

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
      toast('Failed to load more items', 'error')
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

  // Show the hero landing when no filters are active
  const showHero = !hasActiveFilters && !loading

  const navigate = useNavigate()

  const handleAdoptKB = async (kbUuid: string) => {
    try {
      await adoptKnowledgeBase(kbUuid)
      toast('Added to your knowledge bases', 'success')
    } catch {
      toast('Already in your knowledge bases', 'info')
    }
  }

  const handleTryIt = (item: VerifiedCatalogItem) => {
    if (!item.source_uuid) return
    setDetailItem(null)
    if (item.kind === 'workflow') {
      navigate({
        to: '/',
        search: { mode: undefined, tab: undefined, workflow: item.source_uuid, extraction: undefined, automation: undefined, kb: undefined },
      })
    } else if (item.kind === 'search_set') {
      navigate({
        to: '/',
        search: { mode: undefined, tab: undefined, workflow: undefined, extraction: item.source_uuid, automation: undefined, kb: undefined },
      })
    } else if (item.kind === 'knowledge_base') {
      navigate({
        to: '/',
        search: { mode: undefined, tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: item.source_uuid },
      })
    }
  }

  const kindFilters: [KindFilter, string][] = [
    ['', 'All'],
    ['workflow', 'Workflows'],
    ['search_set', 'Extractions'],
    ['knowledge_base', 'Knowledge Bases'],
  ]

  const sortOptions: [SortOption, string][] = [
    ['', 'Newest'],
    ['quality', 'Highest Quality'],
    ['name', 'Name A-Z'],
    ['validations', 'Most Validated'],
  ]

  // Split items by tier for the hero landing
  const goldItems = useMemo(() => items.filter(i => i.quality_tier === 'gold'), [items])
  const otherItems = useMemo(
    () => showHero ? items.filter(i => i.quality_tier !== 'gold') : items,
    [items, showHero],
  )

  return (
    <>
      <div className="flex flex-1 min-h-0">
        {/* Sidebar: Collections */}
        <div className="w-56 shrink-0 border-r border-gray-200 bg-gray-50/50 overflow-y-auto p-3 hidden md:block">
          <button
            onClick={() => setSelectedCollectionId(null)}
            className={`w-full text-left px-3 py-2 rounded-lg text-sm font-medium transition-colors mb-1 ${
              !selectedCollectionId
                ? 'bg-gray-900 text-white'
                : 'text-gray-700 hover:bg-gray-100'
            }`}
          >
            All Items
            <span className={`ml-1.5 text-xs ${!selectedCollectionId ? 'text-gray-300' : 'text-gray-500'}`}>
              {total}
            </span>
          </button>

          {featuredCollections.length > 0 && (
            <div className="mt-4 mb-2">
              <div className="flex items-center gap-1 px-3 mb-1.5">
                <Star className="h-3 w-3 text-yellow-400 fill-current" />
                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Featured</span>
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

          {collections.filter(c => !featuredCollections.some(f => f.id === c.id)).length > 0 && (
            <div className="mt-4 mb-2">
              <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider px-3">Collections</span>
              <div className="mt-1.5 space-y-0.5">
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

        {/* Main content */}
        <div className="flex-1 overflow-y-auto">
          <div className="p-6 max-w-5xl mx-auto">
            {/* Hero header (no filters active) */}
            {showHero && !activeCollection && (
              <div className="mb-8">
                <div className="flex items-center gap-3 mb-2">
                  <div className="flex items-center justify-center h-10 w-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 text-white">
                    <Sparkles className="h-5 w-5" />
                  </div>
                  <div>
                    <h2 className="text-xl font-bold text-gray-900">Explore the Catalog</h2>
                    <p className="text-sm text-gray-500">Validated workflows, extractions, and knowledge bases ready to use</p>
                  </div>
                </div>
              </div>
            )}

            {/* Collection header */}
            {activeCollection && (
              <div className="mb-6">
                <button
                  onClick={() => setSelectedCollectionId(null)}
                  className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 mb-2"
                >
                  <ArrowLeft className="h-3 w-3" /> All Items
                </button>
                <div className="flex items-center gap-2">
                  <FolderOpen className="h-5 w-5 text-gray-400" />
                  <h2 className="text-lg font-bold text-gray-900">{activeCollection.title}</h2>
                  {activeCollection.featured && <Star className="h-4 w-4 text-yellow-400 fill-current" />}
                </div>
                {activeCollection.description && (
                  <p className="text-sm text-gray-500 mt-1 ml-7">{activeCollection.description}</p>
                )}
              </div>
            )}

            {/* Search + Filters */}
            <div className="flex items-center gap-3 mb-4 flex-wrap">
              <div className="relative flex-1 min-w-[200px] max-w-sm">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search items..."
                  className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-200 focus:border-blue-400"
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
                className="px-3 py-1.5 text-xs font-medium border border-gray-300 rounded-lg bg-white text-gray-600 focus:outline-none"
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
                  className="px-2 py-1.5 text-xs font-medium border border-gray-300 rounded-lg bg-white text-gray-600 focus:outline-none"
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
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs bg-blue-50 text-blue-700 border border-blue-200">
                    <Tag className="h-2.5 w-2.5" /> {tagFilter}
                    <button onClick={() => setTagFilter('')} className="hover:text-blue-900 ml-0.5"><X className="h-3 w-3" /></button>
                  </span>
                )}
                {selectedCollectionId && activeCollection && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs bg-gray-100 text-gray-700">
                    <FolderOpen className="h-2.5 w-2.5" /> {activeCollection.title}
                    <button onClick={() => setSelectedCollectionId(null)} className="hover:text-gray-900 ml-0.5"><X className="h-3 w-3" /></button>
                  </span>
                )}
                <button onClick={clearFilters} className="text-xs text-gray-500 hover:text-gray-700 underline">
                  Clear all
                </button>
                <span className="text-xs text-gray-400 ml-auto">{total} result{total !== 1 ? 's' : ''}</span>
              </div>
            )}

            {/* Error state */}
            {error && (
              <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700 mb-4">
                {error}
                <button onClick={refresh} className="ml-2 underline font-medium">Retry</button>
              </div>
            )}

            {/* Loading */}
            {loading ? (
              <div className="flex flex-col items-center justify-center py-20 text-gray-400">
                <Loader2 className="h-8 w-8 animate-spin mb-3" />
                <p className="text-sm">Loading catalog...</p>
              </div>
            ) : items.length === 0 ? (
              /* Empty state */
              <div className="text-center py-20">
                <ShieldCheck className="h-14 w-14 text-gray-200 mx-auto mb-4" />
                <h3 className="text-base font-semibold text-gray-700 mb-1">
                  {hasActiveFilters ? 'No matching items' : 'No verified items yet'}
                </h3>
                <p className="text-sm text-gray-500 max-w-sm mx-auto">
                  {hasActiveFilters
                    ? 'Try broadening your search or removing some filters.'
                    : 'Workflows, extractions, and knowledge bases that have been reviewed and approved by examiners will appear here.'}
                </p>
                {hasActiveFilters && (
                  <button
                    onClick={clearFilters}
                    className="mt-4 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
                  >
                    Clear filters
                  </button>
                )}
              </div>
            ) : (
              <>
                {/* Featured collections (hero landing only) */}
                {showHero && !activeCollection && featuredCollections.length > 0 && (
                  <div className="mb-8">
                    <h3 className="text-sm font-bold text-gray-900 mb-3">Featured Collections</h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                      {featuredCollections.map(col => (
                        <FeaturedCollectionCard
                          key={col.id}
                          collection={col}
                          onClick={() => setSelectedCollectionId(col.id)}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* Gold tier spotlight (hero landing only) */}
                {showHero && !activeCollection && goldItems.length > 0 && (
                  <div className="mb-8">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="h-4 w-4 rounded-full bg-gradient-to-br from-amber-400 to-amber-600" />
                      <h3 className="text-sm font-bold text-gray-900">Top Rated</h3>
                      <span className="text-xs text-gray-400">{goldItems.length} gold-tier item{goldItems.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                      {goldItems.slice(0, 6).map(item => (
                        <CatalogCard
                          key={item.id}
                          item={item}
                          onTagClick={setTagFilter}
                          onClick={() => setDetailItem(item)}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* Main grid */}
                <div className="mb-2">
                  {showHero && !activeCollection && goldItems.length > 0 && (
                    <h3 className="text-sm font-bold text-gray-900 mb-3">All Items</h3>
                  )}
                  {!showHero && !loading && (
                    <div className="text-xs text-gray-400 mb-3">{total} item{total !== 1 ? 's' : ''}</div>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {(showHero && !activeCollection ? otherItems : items).map(item => (
                    <CatalogCard
                      key={item.id}
                      item={item}
                      onTagClick={setTagFilter}
                      onClick={() => setDetailItem(item)}
                    />
                  ))}
                </div>

                {hasMore && (
                  <div className="text-center mt-8">
                    <button
                      onClick={handleLoadMore}
                      disabled={loadingMore}
                      className="inline-flex items-center gap-2 px-6 py-2.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
                    >
                      {loadingMore ? <><Loader2 className="h-4 w-4 animate-spin" /> Loading...</> : `Load more (${total - items.length} remaining)`}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Item detail modal */}
      {detailItem && (
        <ItemDetailModal
          item={detailItem}
          onClose={() => setDetailItem(null)}
          onAddToLibrary={(itm) => { setDetailItem(null); setAddToLibraryItem(itm) }}
          onAdoptKB={handleAdoptKB}
          onTryIt={handleTryIt}
        />
      )}

      {/* Add to library dialog */}
      {addToLibraryItem && libraries.length > 0 && (
        <AddToLibraryDialog
          libraries={libraries}
          itemId={addToLibraryItem.item_id}
          kind={addToLibraryItem.kind as LibraryItemKind}
          onClose={() => setAddToLibraryItem(null)}
          onAdded={() => { setAddToLibraryItem(null); toast('Saved to library', 'success') }}
        />
      )}
    </>
  )
}
