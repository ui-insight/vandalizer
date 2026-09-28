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

  const [collectionsError, setCollectionsError] = useState<string | null>(null)
  const collectionRequest = useRef(0)
  const retryCollections = useCallback(async () => {
    const request = ++collectionRequest.current
    setCollectionsError(null)
    const results = await Promise.allSettled([
      browseCollections(lockedKind || undefined),
      listFeaturedCollections(lockedKind || undefined),
    ])
    if (request !== collectionRequest.current) return
    const [all, featured] = results
    if (all.status === 'fulfilled') setCollections(all.value.collections)
    if (featured.status === 'fulfilled') setFeaturedCollections(featured.value.collections)
    if (results.some(result => result.status === 'rejected')) setCollectionsError('Some collections could not be loaded.')
  }, [lockedKind])
  const invalidateCollections = useCallback(() => { collectionRequest.current++ }, [])
  useEffect(() => { void retryCollections(); return invalidateCollections }, [retryCollections, invalidateCollections])

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

  // A filter change invalidates both the current page and any pending next page.
  const requestVersion = useRef(0)
  const morePending = useRef(false)
  const refresh = useCallback(async () => {
    const request = ++requestVersion.current
    morePending.current = false
    setLoadingMore(false)
    setLoading(true)
    setError(null)
    setItems([])
    setTotal(0)
    try {
      const data = await listVerifiedItems(queryParams(0))
      if (request !== requestVersion.current) return
      setItems(data.items)
      setTotal(data.total)
      if (!narrowed) setAllTotal(data.total)
    } catch {
      if (request === requestVersion.current) setError(loadErrorMessage)
    } finally {
      if (request === requestVersion.current) setLoading(false)
    }
  }, [queryParams, narrowed, loadErrorMessage])

  const invalidateItems = useCallback(() => { requestVersion.current++ }, [])
  useEffect(() => { void refresh(); return invalidateItems }, [refresh, invalidateItems])

  const handleLoadMore = async () => {
    if (morePending.current || loading || items.length >= total) return
    const request = requestVersion.current
    morePending.current = true
    setLoadingMore(true)
    try {
      const data = await listVerifiedItems(queryParams(items.length))
      if (request !== requestVersion.current) return
      setItems(prev => [...prev, ...data.items.filter(item => !prev.some(existing => existing.id === item.id))])
      setTotal(data.total)
    } catch {
      if (request === requestVersion.current) onLoadMoreError('Failed to load more items. Your current results are preserved; retry Load more.')
    } finally {
      if (request === requestVersion.current) { morePending.current = false; setLoadingMore(false) }
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
    setDebouncedSearch('')
    setKindFilter('')
    setQualityFilter('')
    setTagFilter('')
    setSortOption('')
    setSelectedCollectionId(null)
  }

  const hasActiveFilters = !!(kindFilterState || qualityFilter || tagFilter || sortOption || selectedCollectionId || debouncedSearch)
  // Show the hero landing when no filters are active
  const showHero = !hasActiveFilters && !loading && !error

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
    loading, loadingMore, error, collectionsError, retryCollections,
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
