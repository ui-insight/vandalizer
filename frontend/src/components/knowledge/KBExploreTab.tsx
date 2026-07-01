import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Search, ShieldCheck, BookOpen, FolderOpen, Star, X,
  ArrowUpDown, ArrowLeft, Loader2, Tag, Sparkles, User as UserIcon, Mail,
} from 'lucide-react'
import { QualityBadge } from '../library/QualityBadge'
import { ItemDetailModal } from '../library/ExploreTab'
import {
  listVerifiedItems, browseCollections, listFeaturedCollections,
} from '../../api/library'
import { adoptKnowledgeBase } from '../../api/knowledge'
import type {
  VerifiedCatalogItem, VerifiedCollection, AuthorRef,
} from '../../types/library'
import { useToast } from '../../contexts/ToastContext'
import { useWorkspace } from '../../contexts/WorkspaceContext'

type SortOption = '' | 'quality' | 'name' | 'validations'
type QualityFilter = '' | 'gold' | 'silver' | 'bronze'

const PAGE_SIZE = 30

// Dark palette (matches KnowledgePanel)
const C = {
  bg: '#1e1e1e',
  panel: '#191919',
  card: '#262626',
  cardHover: '#2f2f2f',
  border: '#3a3a3a',
  borderHover: '#4a4a4a',
  text: '#e5e5e5',
  textMuted: '#aaa',
  textDim: '#888',
  textFaint: '#666',
}

// ---------------------------------------------------------------------------
// Dark-mode author chip (the shared AuthorChip is built for light backgrounds)
// ---------------------------------------------------------------------------

function DarkAuthorChip({ author, size = 'sm' }: { author: AuthorRef | null | undefined; size?: 'sm' | 'md' }) {
  if (!author) return null
  const display = author.name || author.email || author.user_id
  const fontSize = size === 'sm' ? 11 : 12
  const iconSize = size === 'sm' ? 10 : 12
  const mailto = author.email ? `mailto:${author.email}?subject=${encodeURIComponent('Question about your knowledge base')}` : null

  const body = (
    <>
      <UserIcon size={iconSize} style={{ flexShrink: 0 }} />
      <span style={{ fontWeight: 500 }}>{display}</span>
      {mailto && <Mail size={iconSize} style={{ flexShrink: 0, opacity: 0.6 }} />}
    </>
  )
  const style: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: 4,
    fontSize, color: '#cbd5e1',
    background: 'rgba(255,255,255,0.06)',
    padding: '2px 8px', borderRadius: 999, lineHeight: 1.4,
    whiteSpace: 'nowrap', maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis',
  }
  if (mailto) {
    return (
      <a href={mailto} onClick={(e) => e.stopPropagation()} style={{ ...style, textDecoration: 'none', cursor: 'pointer' }}>
        {body}
      </a>
    )
  }
  return <span style={style}>{body}</span>
}

// ---------------------------------------------------------------------------
// Tier styling
// ---------------------------------------------------------------------------

const TIER_RING = {
  gold: '1px solid rgba(251, 191, 36, 0.45)',
  silver: '1px solid rgba(156, 163, 175, 0.45)',
  bronze: '1px solid rgba(251, 146, 60, 0.4)',
} as const

// ---------------------------------------------------------------------------
// Featured collection card (dark)
// ---------------------------------------------------------------------------

function FeaturedCollectionCard({ collection, onClick }: { collection: VerifiedCollection; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="group"
      style={{
        display: 'flex', flexDirection: 'column', textAlign: 'left',
        padding: 16, borderRadius: 12,
        backgroundColor: C.card, border: `1px solid ${C.border}`,
        cursor: 'pointer', transition: 'all 0.15s', fontFamily: 'inherit',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.backgroundColor = C.cardHover
        e.currentTarget.style.borderColor = C.borderHover
      }}
      onMouseLeave={e => {
        e.currentTarget.style.backgroundColor = C.card
        e.currentTarget.style.borderColor = C.border
      }}
    >
      <div style={{ display: 'flex', alignItems: 'start', gap: 8, marginBottom: 6 }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          height: 32, width: 32, borderRadius: 8,
          backgroundColor: 'rgba(234, 179, 8, 0.15)', color: '#facc15', flexShrink: 0,
        }}>
          <Star size={16} fill="currentColor" />
        </div>
        <h3 style={{ fontSize: 13, fontWeight: 700, color: C.text, flex: 1, minWidth: 0, margin: 0, lineHeight: 1.3 }}>
          {collection.title}
        </h3>
      </div>
      {collection.description && (
        <p style={{ fontSize: 12, color: C.textDim, margin: '0 0 10px 0', lineHeight: 1.4 }}>
          {collection.description}
        </p>
      )}
      <span style={{ marginTop: 'auto', fontSize: 11, fontWeight: 500, color: C.textFaint }}>
        {(collection.visible_count ?? collection.item_ids.length)} item{(collection.visible_count ?? collection.item_ids.length) !== 1 ? 's' : ''}
      </span>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Catalog card (dark, KB-specific)
// ---------------------------------------------------------------------------

function KBCatalogCard({
  item, onTagClick, onClick,
}: {
  item: VerifiedCatalogItem
  onTagClick: (tag: string) => void
  onClick: () => void
}) {
  const tierBorder = item.quality_tier
    ? TIER_RING[item.quality_tier as keyof typeof TIER_RING]
    : `1px solid ${C.border}`

  const tierIconColor =
    item.quality_tier === 'gold' ? '#fbbf24'
    : item.quality_tier === 'silver' ? '#9ca3af'
    : '#34d399'

  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', flexDirection: 'column', textAlign: 'left',
        padding: 14, borderRadius: 12,
        backgroundColor: C.card, border: tierBorder,
        cursor: 'pointer', transition: 'all 0.15s', fontFamily: 'inherit',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.backgroundColor = C.cardHover
      }}
      onMouseLeave={e => {
        e.currentTarget.style.backgroundColor = C.card
      }}
    >
      <div style={{ display: 'flex', alignItems: 'start', gap: 6, marginBottom: 6 }}>
        <ShieldCheck size={14} style={{ color: tierIconColor, flexShrink: 0, marginTop: 2 }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: C.text, flex: 1, minWidth: 0, lineHeight: 1.3 }}>
          {item.display_name || item.name}
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: 4,
          fontSize: 11, padding: '1px 6px', borderRadius: 4,
          backgroundColor: 'rgba(56, 189, 248, 0.12)', color: '#7dd3fc',
          border: '1px solid rgba(56, 189, 248, 0.25)',
        }}>
          <BookOpen size={11} />
          Knowledge Base
        </span>
        <QualityBadge tier={item.quality_tier} score={item.quality_score} />
        {item.validation_run_count > 0 && (
          <span style={{ fontSize: 10, color: C.textFaint }}>
            {item.validation_run_count} val{item.validation_run_count !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {item.description && (
        <p style={{ fontSize: 12, color: '#bdbdbd', margin: '0 0 8px 0', lineHeight: 1.4 }}>
          {item.description}
        </p>
      )}

      {item.created_by && (
        <div style={{ marginBottom: 8 }}>
          <DarkAuthorChip author={item.created_by} />
        </div>
      )}

      {(item.total_sources != null || item.total_chunks != null) && (
        <div style={{ display: 'flex', gap: 12, fontSize: 11, color: C.textFaint, marginBottom: 8 }}>
          {item.total_sources != null && (
            <span>{item.total_sources} source{item.total_sources !== 1 ? 's' : ''}</span>
          )}
          {item.total_chunks != null && (
            <span>{item.total_chunks.toLocaleString()} chunks</span>
          )}
        </div>
      )}

      {item.tags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 'auto', paddingTop: 6 }}>
          {item.tags.slice(0, 4).map((tag, i) => (
            <span
              key={i}
              onClick={(e) => { e.stopPropagation(); onTagClick(tag) }}
              style={{
                fontSize: 10, padding: '1px 6px', borderRadius: 999,
                backgroundColor: 'rgba(255,255,255,0.06)', color: '#c5c5c5',
                cursor: 'pointer', transition: 'background-color 0.15s',
              }}
            >
              {tag}
            </span>
          ))}
          {item.tags.length > 4 && (
            <span style={{ fontSize: 10, color: C.textFaint }}>+{item.tags.length - 4}</span>
          )}
        </div>
      )}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Sidebar collection link (dark)
// ---------------------------------------------------------------------------

function CollectionLink({
  collection, active, onClick,
}: {
  collection: VerifiedCollection
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      style={{
        width: '100%', textAlign: 'left', padding: '8px 10px', borderRadius: 8,
        fontSize: 13, fontFamily: 'inherit',
        backgroundColor: active ? 'rgba(255,255,255,0.08)' : 'transparent',
        color: active ? '#fff' : C.textMuted,
        border: 'none', cursor: 'pointer',
        display: 'flex', alignItems: 'flex-start', gap: 6,
        transition: 'background-color 0.15s',
      }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.04)' }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.backgroundColor = 'transparent' }}
    >
      <FolderOpen size={13} style={{ color: active ? '#cbd5e1' : C.textFaint, flexShrink: 0, marginTop: 2 }} />
      <span style={{ flex: 1, minWidth: 0, lineHeight: 1.3 }}>{collection.title}</span>
      {collection.featured && (
        <Star size={11} fill="currentColor" style={{ color: active ? '#fde047' : '#facc15', flexShrink: 0, marginTop: 3 }} />
      )}
      <span style={{ fontSize: 11, color: active ? '#cbd5e1' : C.textFaint, flexShrink: 0, marginTop: 1 }}>
        {collection.visible_count ?? collection.item_ids.length}
      </span>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Main KBExploreTab
// ---------------------------------------------------------------------------

interface KBExploreTabProps {
  /** Called after a verified KB has been adopted into the user's library, so the parent can refresh its My KBs list. */
  onAdopted?: () => void
}

export function KBExploreTab({ onAdopted }: KBExploreTabProps) {
  const { toast } = useToast()
  const { activateKB } = useWorkspace()

  // Data
  const [items, setItems] = useState<VerifiedCatalogItem[]>([])
  const [total, setTotal] = useState(0)
  const [collections, setCollections] = useState<VerifiedCollection[]>([])
  const [featuredCollections, setFeaturedCollections] = useState<VerifiedCollection[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Filters (kind locked to knowledge_base)
  const [searchQuery, setSearchQuery] = useState('')
  const [qualityFilter, setQualityFilter] = useState<QualityFilter>('')
  const [tagFilter, setTagFilter] = useState('')
  const [sortOption, setSortOption] = useState<SortOption>('')
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null)

  const [detailItem, setDetailItem] = useState<VerifiedCatalogItem | null>(null)

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
      .catch(() => {})
    listFeaturedCollections()
      .then(d => setFeaturedCollections(d.collections))
      .catch(() => {})
  }, [])

  // Fetch items when filters change (kind always knowledge_base)
  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listVerifiedItems({
        kind: 'knowledge_base',
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
      setError('Failed to load knowledge bases. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [debouncedSearch, qualityFilter, tagFilter, sortOption, selectedCollectionId])

  useEffect(() => { refresh() }, [refresh])

  const handleLoadMore = async () => {
    setLoadingMore(true)
    try {
      const data = await listVerifiedItems({
        kind: 'knowledge_base',
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
    setQualityFilter('')
    setTagFilter('')
    setSortOption('')
    setSelectedCollectionId(null)
  }

  const hasActiveFilters = !!(qualityFilter || tagFilter || sortOption || selectedCollectionId || debouncedSearch)

  // Show the hero landing when no filters are active
  const showHero = !hasActiveFilters && !loading

  const handleAdoptKB = async (kbUuid: string) => {
    try {
      await adoptKnowledgeBase(kbUuid)
      toast('Added to your knowledge bases', 'success')
      onAdopted?.()
    } catch {
      toast('Already in your knowledge bases', 'info')
    }
  }

  const handleTryIt = (item: VerifiedCatalogItem) => {
    if (!item.source_uuid) return
    setDetailItem(null)
    activateKB(item.source_uuid, item.display_name || item.name)
  }

  const sortOptions: [SortOption, string][] = [
    ['', 'Newest'],
    ['quality', 'Highest Quality'],
    ['name', 'Name A-Z'],
    ['validations', 'Most Validated'],
  ]

  const goldItems = useMemo(() => items.filter(i => i.quality_tier === 'gold'), [items])
  const otherItems = useMemo(
    () => showHero ? items.filter(i => i.quality_tier !== 'gold') : items,
    [items, showHero],
  )

  const regularCollections = collections.filter(c => !featuredCollections.some(f => f.id === c.id))

  return (
    <>
      <div style={{
        display: 'flex', flex: 1, minHeight: 0,
        backgroundColor: C.bg, color: C.text,
      }}>
        {/* Sidebar: Collections */}
        <div style={{
          width: 224, flexShrink: 0,
          borderRight: `1px solid ${C.border}`,
          backgroundColor: C.panel,
          overflowY: 'auto', padding: 12,
        }}
          className="hidden md:block"
        >
          <button
            onClick={() => setSelectedCollectionId(null)}
            style={{
              width: '100%', textAlign: 'left', padding: '8px 10px', borderRadius: 8,
              fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
              backgroundColor: !selectedCollectionId ? 'rgba(255,255,255,0.08)' : 'transparent',
              color: !selectedCollectionId ? '#fff' : C.textMuted,
              border: 'none', cursor: 'pointer', marginBottom: 4,
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            }}
          >
            <span>All Knowledge Bases</span>
            <span style={{ fontSize: 11, color: !selectedCollectionId ? '#cbd5e1' : C.textFaint }}>{total}</span>
          </button>

          {featuredCollections.length > 0 && (
            <div style={{ marginTop: 16, marginBottom: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '0 10px', marginBottom: 6 }}>
                <Star size={10} fill="currentColor" style={{ color: '#facc15' }} />
                <span style={{ fontSize: 10, fontWeight: 700, color: C.textFaint, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  Featured
                </span>
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

          {regularCollections.length > 0 && (
            <div style={{ marginTop: 16, marginBottom: 8 }}>
              <span style={{
                fontSize: 10, fontWeight: 700, color: C.textFaint,
                textTransform: 'uppercase', letterSpacing: '0.08em', padding: '0 10px',
              }}>
                Collections
              </span>
              <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 2 }}>
                {regularCollections.map(col => (
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
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <div style={{ padding: 24, maxWidth: 1024, margin: '0 auto' }}>
            {/* Hero header */}
            {showHero && !activeCollection && (
              <div style={{ marginBottom: 24 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    height: 40, width: 40, borderRadius: 12,
                    background: 'linear-gradient(135deg, #38bdf8 0%, #6366f1 100%)',
                    color: '#fff',
                  }}>
                    <Sparkles size={20} />
                  </div>
                  <div>
                    <h2 style={{ fontSize: 20, fontWeight: 700, color: '#fff', margin: 0 }}>
                      Explore Knowledge Bases
                    </h2>
                    <p style={{ fontSize: 13, color: C.textDim, margin: '2px 0 0' }}>
                      Verified knowledge bases ready to chat with
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Collection header */}
            {activeCollection && (
              <div style={{ marginBottom: 20 }}>
                <button
                  onClick={() => setSelectedCollectionId(null)}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 4,
                    fontSize: 11, color: C.textDim, background: 'transparent',
                    border: 'none', cursor: 'pointer', marginBottom: 6, fontFamily: 'inherit',
                  }}
                >
                  <ArrowLeft size={12} /> All Knowledge Bases
                </button>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <FolderOpen size={18} style={{ color: C.textDim }} />
                  <h2 style={{ fontSize: 18, fontWeight: 700, color: '#fff', margin: 0 }}>
                    {activeCollection.title}
                  </h2>
                  {activeCollection.featured && (
                    <Star size={14} fill="currentColor" style={{ color: '#facc15' }} />
                  )}
                </div>
                {activeCollection.description && (
                  <p style={{ fontSize: 13, color: C.textDim, marginTop: 4, marginLeft: 26 }}>
                    {activeCollection.description}
                  </p>
                )}
              </div>
            )}

            {/* Search + Filters */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
              <div style={{ position: 'relative', flex: 1, minWidth: 200, maxWidth: 360 }}>
                <Search size={16} style={{
                  position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
                  color: C.textFaint, pointerEvents: 'none',
                }} aria-hidden="true" />
                <input
                  type="search"
                  aria-label="Search knowledge bases"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search knowledge bases..."
                  style={{
                    width: '100%', padding: '7px 10px 7px 32px',
                    fontSize: 13, fontFamily: 'inherit',
                    backgroundColor: C.card, color: C.text,
                    border: `1px solid ${C.border}`, borderRadius: 8,
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              <select
                aria-label="Filter by quality tier"
                value={qualityFilter}
                onChange={(e) => setQualityFilter(e.target.value as QualityFilter)}
                style={{
                  padding: '6px 10px', fontSize: 12, fontWeight: 500, fontFamily: 'inherit',
                  border: `1px solid ${C.border}`, borderRadius: 8,
                  backgroundColor: C.card, color: C.textMuted, cursor: 'pointer',
                }}
              >
                <option value="">Any quality</option>
                <option value="gold">Gold</option>
                <option value="silver">Silver</option>
                <option value="bronze">Bronze</option>
              </select>

              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <ArrowUpDown size={13} style={{ color: C.textFaint }} aria-hidden="true" />
                <select
                  aria-label="Sort knowledge bases"
                  value={sortOption}
                  onChange={(e) => setSortOption(e.target.value as SortOption)}
                  style={{
                    padding: '6px 10px', fontSize: 12, fontWeight: 500, fontFamily: 'inherit',
                    border: `1px solid ${C.border}`, borderRadius: 8,
                    backgroundColor: C.card, color: C.textMuted, cursor: 'pointer',
                  }}
                >
                  {sortOptions.map(([val, label]) => (
                    <option key={val} value={val}>{label}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Active filter chips */}
            {hasActiveFilters && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
                {tagFilter && (
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', gap: 4,
                    padding: '3px 10px', borderRadius: 999, fontSize: 11,
                    backgroundColor: 'rgba(56, 189, 248, 0.12)', color: '#7dd3fc',
                    border: '1px solid rgba(56, 189, 248, 0.25)',
                  }}>
                    <Tag size={10} aria-hidden="true" /> {tagFilter}
                    <button
                      type="button"
                      aria-label={`Remove tag filter ${tagFilter}`}
                      onClick={() => setTagFilter('')}
                      style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'inherit', marginLeft: 2, display: 'flex', padding: 0 }}
                    >
                      <X size={11} aria-hidden="true" />
                    </button>
                  </span>
                )}
                {selectedCollectionId && activeCollection && (
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', gap: 4,
                    padding: '3px 10px', borderRadius: 999, fontSize: 11,
                    backgroundColor: 'rgba(255,255,255,0.06)', color: C.text,
                  }}>
                    <FolderOpen size={10} aria-hidden="true" /> {activeCollection.title}
                    <button
                      type="button"
                      aria-label={`Remove collection filter ${activeCollection.title}`}
                      onClick={() => setSelectedCollectionId(null)}
                      style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'inherit', marginLeft: 2, display: 'flex', padding: 0 }}
                    >
                      <X size={11} aria-hidden="true" />
                    </button>
                  </span>
                )}
                <button
                  onClick={clearFilters}
                  style={{
                    fontSize: 11, color: C.textDim, background: 'transparent',
                    border: 'none', cursor: 'pointer', textDecoration: 'underline', fontFamily: 'inherit',
                  }}
                >
                  Clear all
                </button>
                <span role="status" aria-live="polite" style={{ fontSize: 11, color: C.textFaint, marginLeft: 'auto' }}>
                  {total} result{total !== 1 ? 's' : ''}
                </span>
              </div>
            )}

            {/* Error state */}
            {error && (
              <div role="alert" style={{
                borderRadius: 8, padding: '10px 14px', fontSize: 13,
                color: '#fca5a5', backgroundColor: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid rgba(239, 68, 68, 0.25)', marginBottom: 14,
              }}>
                {error}
                <button
                  type="button"
                  onClick={refresh}
                  style={{
                    marginLeft: 8, textDecoration: 'underline', fontWeight: 500,
                    color: 'inherit', background: 'transparent', border: 'none', cursor: 'pointer', fontFamily: 'inherit',
                  }}
                >
                  Retry
                </button>
              </div>
            )}

            {/* Loading */}
            {loading ? (
              <div role="status" aria-live="polite" style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                justifyContent: 'center', padding: '80px 0', color: C.textFaint,
              }}>
                <Loader2 size={28} style={{ animation: 'spin 1s linear infinite', marginBottom: 10 }} aria-hidden="true" />
                <p style={{ fontSize: 13, margin: 0 }}>Loading knowledge bases...</p>
              </div>
            ) : items.length === 0 ? (
              <div role="status" aria-live="polite" style={{ textAlign: 'center', padding: '80px 16px' }}>
                <BookOpen size={48} style={{ color: '#404040', margin: '0 auto 14px' }} aria-hidden="true" />
                <h3 style={{ fontSize: 15, fontWeight: 600, color: C.text, marginBottom: 4 }}>
                  {hasActiveFilters ? 'No matching knowledge bases' : 'No verified knowledge bases yet'}
                </h3>
                <p style={{ fontSize: 13, color: C.textDim, maxWidth: 340, margin: '0 auto' }}>
                  {hasActiveFilters
                    ? 'Try broadening your search or removing some filters.'
                    : 'Knowledge bases that have been reviewed and approved by examiners will appear here.'}
                </p>
                {hasActiveFilters && (
                  <button
                    type="button"
                    onClick={clearFilters}
                    style={{
                      marginTop: 16, padding: '6px 14px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                      color: C.text, backgroundColor: C.card,
                      border: `1px solid ${C.border}`, borderRadius: 8, cursor: 'pointer',
                    }}
                  >
                    Clear filters
                  </button>
                )}
              </div>
            ) : (
              <>
                {/* Featured collections (hero landing only) */}
                {showHero && !activeCollection && featuredCollections.length > 0 && (
                  <div style={{ marginBottom: 28 }}>
                    <h3 style={{ fontSize: 13, fontWeight: 700, color: C.text, marginBottom: 10 }}>
                      Featured Collections
                    </h3>
                    <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))' }}>
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

                {/* Gold tier spotlight */}
                {showHero && !activeCollection && goldItems.length > 0 && (
                  <div style={{ marginBottom: 28 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                      <div style={{
                        height: 14, width: 14, borderRadius: 999,
                        background: 'linear-gradient(135deg, #fbbf24 0%, #d97706 100%)',
                      }} />
                      <h3 style={{ fontSize: 13, fontWeight: 700, color: C.text, margin: 0 }}>
                        Top Rated
                      </h3>
                      <span style={{ fontSize: 11, color: C.textFaint }}>
                        {goldItems.length} gold-tier item{goldItems.length !== 1 ? 's' : ''}
                      </span>
                    </div>
                    <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))' }}>
                      {goldItems.slice(0, 6).map(item => (
                        <KBCatalogCard
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
                <div style={{ marginBottom: 6 }}>
                  {showHero && !activeCollection && goldItems.length > 0 && (
                    <h3 style={{ fontSize: 13, fontWeight: 700, color: C.text, marginBottom: 10 }}>All Items</h3>
                  )}
                  {!showHero && !loading && (
                    <div role="status" aria-live="polite" style={{ fontSize: 11, color: C.textFaint, marginBottom: 10 }}>
                      {total} item{total !== 1 ? 's' : ''}
                    </div>
                  )}
                </div>

                <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))' }}>
                  {(showHero && !activeCollection ? otherItems : items).map(item => (
                    <KBCatalogCard
                      key={item.id}
                      item={item}
                      onTagClick={setTagFilter}
                      onClick={() => setDetailItem(item)}
                    />
                  ))}
                </div>

                {hasMore && (
                  <div style={{ textAlign: 'center', marginTop: 28 }}>
                    <button
                      type="button"
                      onClick={handleLoadMore}
                      disabled={loadingMore}
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: 8,
                        padding: '8px 20px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                        color: C.text, backgroundColor: C.card,
                        border: `1px solid ${C.border}`, borderRadius: 8,
                        cursor: loadingMore ? 'default' : 'pointer',
                        opacity: loadingMore ? 0.6 : 1,
                      }}
                    >
                      {loadingMore ? (
                        <>
                          <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" />
                          Loading...
                        </>
                      ) : `Load more (${total - items.length} remaining)`}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {detailItem && (
        <ItemDetailModal
          item={detailItem}
          onClose={() => setDetailItem(null)}
          onAddToLibrary={() => {}}
          onAdoptKB={async (uuid) => {
            await handleAdoptKB(uuid)
            setDetailItem(null)
          }}
          onTryIt={handleTryIt}
        />
      )}
    </>
  )
}
