import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { listVerifiedItems, browseCollections, listFeaturedCollections } from '../../api/library'
import type { VerifiedCatalogItem, VerifiedCollection } from '../../types/library'

/**
 * The catalog browser's state, fetching, filters and hero split — shared by
 * the Library "Explore Catalog" tab and the Knowledge "Explore Knowledge
 * Bases" tab (#916). The two surfaces keep their own rendering (light
 * Tailwind vs. the dark inline-styled KB panel); everything that had drifted
 * between them — tier vocabulary, filter and sort options, pagination, the
 * "Top Rated" split — lives here once.
 */

export type KindFilter = '' | 'workflow' | 'search_set' | 'knowledge_base'
export type SortOption = '' | 'quality' | 'name' | 'adoption' | 'validations'
// Keyed on the tiers compute_quality_tier emits — the only vocabulary a
// measured item can carry.
export type QualityFilter = '' | 'excellent' | 'good' | 'fair'

export const CATALOG_PAGE_SIZE = 30

export const SORT_OPTIONS: [SortOption, string][] = [
  ['', 'Newest'],
  ['quality', 'Highest Quality'],
  ['name', 'Name A-Z'],
  ['adoption', 'Most Used'],
  ['validations', 'Most Validated'],
]

export const QUALITY_FILTER_OPTIONS: [QualityFilter, string][] = [
  ['', 'Any quality'],
  ['excellent', 'Excellent'],
  ['good', 'Good'],
  ['fair', 'Fair'],
]

/** Measured top-tier items lead the spotlight; hand-asserted ones follow. Both
 *  stay eligible so a fresh install still has a landing page, but the earned
 *  rating always outranks the typed one. */
export function spotlightOrder(a: VerifiedCatalogItem, b: VerifiedCatalogItem): number {
  return Number(!!a.quality_asserted) - Number(!!b.quality_asserted)
}

interface Options {
  /** Pin the browser to one kind (the KB tab); the kind filter is then inert. */
  lockedKind?: KindFilter
  loadErrorMessage: string
  onLoadMoreError: (message: string) => void
}

export function useCatalogBrowser({ lockedKind, loadErrorMessage, onLoadMoreError }: Options) {
  // Data
  const [items, setItems] = useState<VerifiedCatalogItem[]>([])
  const [total, setTotal] = useState(0)
  // Unfiltered count for the "All …" badge — `total` tracks the active query,
  // so it shrinks whenever a kind/collection/search filter is on.
  const [allTotal, setAllTotal] = useState<number | null>(null)
  const [collections, setCollections] = useState<VerifiedCollection[]>([])
  const [featuredCollections, setFeaturedCollections] = useState<VerifiedCollection[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [searchQuery, setSearchQuery] = useState('')
  const [kindFilterState, setKindFilter] = useState<KindFilter>('')
  const kindFilter: KindFilter = lockedKind ?? kindFilterState
  const [qualityFilter, setQualityFilter] = useState<QualityFilter>('')
  const [tagFilter, setTagFilter] = useState('')
  const [sortOption, setSortOption] = useState<SortOption>('')
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null)

  // Debounced search
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [debouncedSearch, setDebouncedSearch] = useState('')
  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    searchTimerRef.current = setTimeout(() => setDebouncedSearch(searchQuery), 300)
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current) }
  }, [searchQuery])

  // Load collections once (counts scoped to the locked kind when there is one)
  useEffect(() => {
    browseCollections(lockedKind || undefined)
      .then(d => setCollections(d.collections))
      // The knowledge-base tab never surfaced this (its Retry does not refetch
      // collections); keep that, and report it where the library tab always did.
      .catch(() => { if (!lockedKind) setError('Failed to load collections') })
    listFeaturedCollections(lockedKind || undefined)
      .then(d => setFeaturedCollections(d.collections))
      .catch(() => {})
  }, [lockedKind])

  const queryParams = useCallback((skip: number) => ({
    kind: kindFilter || undefined,
    search: debouncedSearch || undefined,
    quality_tier: qualityFilter || undefined,
    tag: tagFilter || undefined,
    collection_id: selectedCollectionId || undefined,
    sort: sortOption || undefined,
    skip,
    limit: CATALOG_PAGE_SIZE,
  }), [kindFilter, debouncedSearch, qualityFilter, tagFilter, selectedCollectionId, sortOption])

  // Only the user-chosen kind narrows; a locked kind is the whole population.
  const narrowed = !!(kindFilterState || debouncedSearch || qualityFilter || tagFilter || selectedCollectionId)

  // Fetch items when filters change
  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listVerifiedItems(queryParams(0))
      setItems(data.items)
      setTotal(data.total)
      // Sort doesn't change the result count, so any fetch without narrowing
      // filters carries the true "all items" total.
      if (!narrowed) setAllTotal(data.total)
    } catch {
      setError(loadErrorMessage)
    } finally {
      setLoading(false)
    }
  }, [queryParams, narrowed, loadErrorMessage])

  useEffect(() => { refresh() }, [refresh])

  const handleLoadMore = async () => {
    setLoadingMore(true)
    try {
      const data = await listVerifiedItems(queryParams(items.length))
      setItems(prev => [...prev, ...data.items])
    } catch {
      onLoadMoreError('Failed to load more items')
    } finally {
      setLoadingMore(false)
    }
  }

  const hasMore = items.length < total
  const activeCollection = selectedCollectionId
    ? collections.find(c => c.id === selectedCollectionId) ?? null
    : null
  const regularCollections = useMemo(
    () => collections.filter(c => !featuredCollections.some(f => f.id === c.id)),
    [collections, featuredCollections],
  )

  const clearFilters = () => {
    setSearchQuery('')
    setKindFilter('')
    setQualityFilter('')
    setTagFilter('')
    setSortOption('')
    setSelectedCollectionId(null)
  }

  const hasActiveFilters = !!(kindFilterState || qualityFilter || tagFilter || sortOption || selectedCollectionId || debouncedSearch)
  // Show the hero landing when no filters are active
  const showHero = !hasActiveFilters && !loading

  // Split items by tier for the hero landing
  const topItems = useMemo(
    () => items.filter(i => i.quality_tier === 'excellent').sort(spotlightOrder),
    [items],
  )
  const otherItems = useMemo(
    () => showHero ? items.filter(i => i.quality_tier !== 'excellent') : items,
    [items, showHero],
  )

  return {
    items, total, allTotal, collections, featuredCollections, regularCollections,
    loading, loadingMore, error,
    searchQuery, setSearchQuery,
    kindFilter, setKindFilter,
    qualityFilter, setQualityFilter,
    tagFilter, setTagFilter,
    sortOption, setSortOption,
    selectedCollectionId, setSelectedCollectionId,
    debouncedSearch,
    refresh, handleLoadMore, hasMore,
    activeCollection, clearFilters, hasActiveFilters, showHero,
    topItems, otherItems,
  }
}
