import { useCallback, useEffect, useState } from 'react'
import { Search, ShieldCheck, Beaker, BookOpen, Workflow, Database, ChevronDown, ChevronUp } from 'lucide-react'
import { AppLayout } from '../components/layout/AppLayout'
import { QualityBadge } from '../components/library/QualityBadge'
import { listVerifiedItems, listFeaturedCollections, tryVerifiedItem } from '../api/library'
import type { VerifiedCatalogItem, VerifiedCollection } from '../types/library'

type KindFilter = '' | 'workflow' | 'search_set' | 'knowledge_base'

function KindIcon({ kind }: { kind: string }) {
  if (kind === 'workflow') return <Workflow className="h-4 w-4 text-purple-500" />
  if (kind === 'knowledge_base') return <Database className="h-4 w-4 text-sky-500" />
  return <BookOpen className="h-4 w-4 text-teal-500" />
}

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

function CatalogCard({ item }: { item: VerifiedCatalogItem }) {
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
              <span key={i} className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                {tag}
              </span>
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

function FeaturedCollectionCard({ collection, items }: { collection: VerifiedCollection; items: VerifiedCatalogItem[] }) {
  const collectionItems = items.filter(i => collection.item_ids.includes(i.item_id))
  if (collectionItems.length === 0) return null

  return (
    <div className="border border-gray-200 rounded-lg bg-white p-4">
      <h3 className="text-sm font-semibold text-gray-900 mb-1">{collection.title}</h3>
      {collection.description && (
        <p className="text-xs text-gray-500 mb-3">{collection.description}</p>
      )}
      <div className="space-y-2">
        {collectionItems.slice(0, 5).map(item => (
          <div key={item.id} className="flex items-center gap-2 text-xs">
            <KindIcon kind={item.kind} />
            <span className="text-gray-700 truncate">{item.display_name || item.name}</span>
            <QualityBadge tier={item.quality_tier} score={item.quality_score} />
          </div>
        ))}
        {collectionItems.length > 5 && (
          <p className="text-xs text-gray-400">+{collectionItems.length - 5} more</p>
        )}
      </div>
    </div>
  )
}

export default function Catalog() {
  const [items, setItems] = useState<VerifiedCatalogItem[]>([])
  const [collections, setCollections] = useState<VerifiedCollection[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [kindFilter, setKindFilter] = useState<KindFilter>('')

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listVerifiedItems(kindFilter || undefined, searchQuery || undefined)
      setItems(data.items)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [kindFilter, searchQuery])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    listFeaturedCollections().then(d => setCollections(d.collections)).catch(() => {})
  }, [])

  const filters: [KindFilter, string][] = [
    ['', 'All'],
    ['workflow', 'Workflows'],
    ['search_set', 'Extractions'],
    ['knowledge_base', 'Knowledge Bases'],
  ]

  return (
    <AppLayout>
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <ShieldCheck className="h-6 w-6 text-green-600" />
          <div>
            <h1 className="text-xl font-bold text-gray-900">Verified Catalog</h1>
            <p className="text-sm text-gray-500">
              Browse validated and examiner-approved workflows, extractions, and knowledge bases
            </p>
          </div>
        </div>

        {/* Featured collections */}
        {collections.length > 0 && !searchQuery && !kindFilter && (
          <div className="mb-6">
            <h2 className="text-sm font-semibold text-gray-700 mb-3">Featured Collections</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {collections.map(col => (
                <FeaturedCollectionCard key={col.id} collection={col} items={items} />
              ))}
            </div>
          </div>
        )}

        {/* Search + filter */}
        <div className="flex items-center gap-3 mb-4 flex-wrap">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search verified items..."
              className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
            />
          </div>
          <div className="flex items-center gap-2">
            {filters.map(([val, label]) => (
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
        </div>

        {/* Results */}
        {loading ? (
          <div className="text-sm text-gray-500 py-12 text-center">Loading...</div>
        ) : items.length === 0 ? (
          <div className="text-center py-16">
            <ShieldCheck className="h-12 w-12 text-gray-300 mx-auto mb-3" />
            <h3 className="text-sm font-medium text-gray-700 mb-1">No verified items yet</h3>
            <p className="text-xs text-gray-500">
              Items submitted by your team and approved by examiners will appear here.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {items.map(item => (
              <CatalogCard key={item.id} item={item} />
            ))}
          </div>
        )}
      </div>
    </AppLayout>
  )
}
