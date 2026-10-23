import { useAdminQuery } from '../admin/shared/useAdminQuery'
import { usePanelEffect } from '../shared/usePanelEffect'
import { useCallback, useEffect, useRef, useState } from 'react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { Search, ShieldCheck, X, Pencil, ShieldOff, Tag, FolderPlus, Download, Upload } from 'lucide-react'
import { QualityContractBadge } from './QualityContractBadge'
import { useToast } from '../../contexts/ToastContext'
import { CatalogImportDialog } from './CatalogImportDialog'
import { AuthorChip } from '../shared/AuthorChip'
import { listVerifiedItems, updateItemMetadata, unverifyItem, listCollections, addToCollection, exportCatalogUrl, previewCatalogImport } from '../../api/library'
import type { CatalogPreviewItem } from '../../api/library'
import type { VerifiedCatalogItem, VerifiedCollection } from '../../types/library'
import { listOrganizationsFlat } from '../../api/organizations'
import { useConfirm } from '../shared/useConfirm'

type KindFilter = '' | 'workflow' | 'search_set' | 'knowledge_base'
type QualityFilter = '' | 'excellent' | 'good' | 'fair'

function meetsQualityFilter(tier: string | null, filter: QualityFilter): boolean {
  if (!filter) return true
  if (!tier) return false
  const order = ['fair', 'good', 'excellent']
  return order.indexOf(tier) >= order.indexOf(filter)
}

function KindBadge({ kind }: { kind: string }) {
  if (kind === 'workflow') {
    return (
      <span className="text-xs px-2 py-0.5 rounded border bg-purple-50 text-purple-700 border-purple-200">
        Workflow
      </span>
    )
  }
  if (kind === 'knowledge_base') {
    return (
      <span className="text-xs px-2 py-0.5 rounded border bg-sky-50 text-sky-700 border-sky-200">
        Knowledge Base
      </span>
    )
  }
  return (
    <span className="text-xs px-2 py-0.5 rounded border bg-teal-50 text-teal-700 border-teal-200">
      Extraction
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
  const [selectedOrgIds, setSelectedOrgIds] = useState<string[]>(item.organization_ids || [])
  const { data: orgData, error: orgError, load: reloadOrgs } = useAdminQuery(listOrganizationsFlat)
  const allOrgs = orgData?.organizations ?? []
  const [saving, setSaving] = useState(false)
  const [showPreview, setShowPreview] = useState(false)

  const pending = useRef(false)
  const dialogRef = useRef<HTMLDivElement>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  usePanelEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape' && !pending.current) onClose() }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const toggleOrg = (uuid: string) => {
    setSelectedOrgIds(prev =>
      prev.includes(uuid) ? prev.filter(id => id !== uuid) : [...prev, uuid]
    )
  }

  const handleSave = async () => {
    if (pending.current) return
    pending.current = true; setSaveError(null)
    setSaving(true)
    try {
      await updateItemMetadata(item.kind, item.item_id, {
        display_name: displayName || undefined,
        description: description || undefined,
        markdown: markdown || undefined,
        organization_ids: selectedOrgIds,
      })
      onSaved()
      onClose()
    } catch (reason) { setSaveError(reason instanceof Error ? reason.message : 'Could not save metadata. Your draft is preserved.') } finally {
      pending.current = false
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4" style={{ zIndex: 700 }}>
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, fallbackFocus: () => dialogRef.current!, tabbableOptions: { displayCheck: 'none' } }}>
      <div ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-label="Edit Metadata" className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90dvh] min-w-0 flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <h3 className="text-base font-semibold text-gray-900">Edit Metadata</h3>
          <button type="button" disabled={saving} onClick={onClose} aria-label="Close" className="p-1 rounded hover:bg-gray-100 text-gray-500">
            <X className="h-5 w-5" />
          </button>
        </div>
        <fieldset disabled={saving} className="flex min-h-0 min-w-0 flex-1 flex-col border-0 p-0 m-0">
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {saveError && <p role="alert" className="text-sm text-red-800">{saveError} Your draft is preserved; retry Save.</p>}
          {orgError && <p role="alert" className="text-sm text-red-800">Organization choices could not load. Existing assignments are retained. <button onClick={reloadOrgs} className="underline">Retry organizations</button></p>}
          <div className="text-xs text-gray-600 flex flex-wrap items-center gap-2">
            <KindBadge kind={item.kind} />
            <span className="font-mono break-all">{item.name}</span>
          </div>
          <div>
            <label htmlFor="metadata-display-name" className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
            <input
              id="metadata-display-name"
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder={item.name}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
            />
          </div>
          <div>
            <label htmlFor="metadata-description" className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              id="metadata-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Brief description..."
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
            />
          </div>
          <div>
            <div className="flex items-center justify-between mb-1">
              <label htmlFor="metadata-markdown" className="text-sm font-medium text-gray-700">Documentation (Markdown)</label>
              <button
                type="button"
                onClick={() => setShowPreview(!showPreview)}
                aria-expanded={showPreview}
                className="text-xs text-gray-500 hover:text-gray-700"
              >
                {showPreview ? 'Edit' : 'Preview'}
              </button>
            </div>
            {showPreview ? (
              <div className="border border-gray-300 rounded-md p-3 min-h-[120px] text-sm text-gray-700 prose prose-sm max-w-none whitespace-pre-wrap">
                {markdown || <span className="text-gray-500 italic">No documentation</span>}
              </div>
            ) : (
              <textarea
                id="metadata-markdown"
                value={markdown}
                onChange={(e) => setMarkdown(e.target.value)}
                rows={6}
                placeholder="Detailed documentation in markdown..."
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-y font-mono focus:outline-none focus:ring-1 focus:ring-gray-400"
              />
            )}
          </div>
          {allOrgs.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Organization Visibility</label>
              <p className="text-xs text-gray-500 mb-2">
                No orgs selected = visible to everyone. Selected orgs restrict visibility to users in those orgs and below.
              </p>
              <div className="space-y-1.5 max-h-40 overflow-y-auto">
                {allOrgs.map(org => (
                  <label key={org.uuid} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-gray-50 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedOrgIds.includes(org.uuid)}
                      onChange={() => toggleOrg(org.uuid)}
                      className="rounded border-gray-300"
                    />
                    <span className="text-sm text-gray-700">{org.name}</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                      org.org_type === 'university' ? 'bg-purple-100 text-purple-700' :
                      org.org_type === 'college' ? 'bg-blue-100 text-blue-700' :
                      org.org_type === 'department' ? 'bg-green-100 text-green-700' :
                      'bg-gray-100 text-gray-600'
                    }`}>{org.org_type}</span>
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
        </fieldset>
      </div>
      </FocusTrap>
    </div>
  )
}

function CollectionPicker({
  itemId,
  collections,
  onAdded, unavailable = false,
}: {
  itemId: string
  collections: VerifiedCollection[]
  onAdded: () => void
  unavailable?: boolean
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const pending = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const handleAdd = async (colId: string) => {
    if (pending.current) return
    pending.current = true; setBusy(true); setError(null)
    try { await addToCollection(colId, itemId); onAdded(); setOpen(false) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not add to the collection. Retry the choice.') }
    finally { pending.current = false; setBusy(false) }
  }

  // Filter to collections that don't already contain this item
  const available = collections.filter(c => !c.item_ids.includes(itemId))

  return (
    <div ref={ref} className="relative" onKeyDown={event => { if (event.key === 'Escape' && !busy) { setOpen(false); ref.current?.querySelector('button')?.focus() } }}>
      <button
        disabled={busy || unavailable} aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="p-1.5 rounded hover:bg-gray-100 text-gray-500"
        title="Add to Collection"
      >
        <FolderPlus className="h-4 w-4" />
      </button>
      {open && (
        <div className="absolute left-0 sm:left-auto sm:right-0 top-full mt-1 z-20 w-52 max-w-[calc(100vw-64px)] bg-white border border-gray-200 rounded-lg shadow-lg py-1">
          {error && <p role="alert" className="p-3 text-xs text-red-800">{error}</p>}
          {available.length === 0 ? (
            <div className="px-3 py-2 text-xs text-gray-500">
              {collections.length === 0 ? 'No collections exist' : 'Already in all collections'}
            </div>
          ) : (
            available.map(col => (
              <button
                key={col.id}
                disabled={busy}
                onClick={() => handleAdd(col.id)}
                className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 truncate"
              >
                {col.title}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}

export function VerifiedCatalog() {
  const confirm = useConfirm()
  const { toast } = useToast()
  const [searchQuery, setSearchQuery] = useState('')
  const [kindFilter, setKindFilter] = useState<KindFilter>('')
  const [qualityFilter, setQualityFilter] = useState<QualityFilter>('')
  const [editingItem, setEditingItem] = useState<VerifiedCatalogItem | null>(null)
  const [orgMap, setOrgMap] = useState<Record<string, string>>({})
  const { data: collectionData, error: collectionError, load: refreshCollections } = useAdminQuery(listCollections)
  const collections = collectionData?.collections ?? []
  const [pageIndex, setPageIndex] = useState(0)
  const [removing, setRemoving] = useState<string | null>(null)
  const removePending = useRef(false)
  const [importPreview, setImportPreview] = useState<CatalogPreviewItem[] | null>(null)
  const [importFile, setImportFile] = useState<File | null>(null)
  const importInputRef = useRef<HTMLInputElement>(null)

  // Load orgs and collections
  useEffect(() => {
    listOrganizationsFlat()
      .then(data => {
        const map: Record<string, string> = {}
        for (const o of data.organizations) map[o.uuid] = o.name
        setOrgMap(map)
      })
      .catch(() => {})
  }, [])

  const request = useCallback(() => listVerifiedItems({ kind: kindFilter || undefined, search: searchQuery || undefined, skip: pageIndex * 200, limit: 200 }), [kindFilter, searchQuery, pageIndex])
  const { data, loading, error, load: refresh } = useAdminQuery(request)
  const items = data?.items ?? []
  const shown = items.filter(item => meetsQualityFilter(item.quality_tier, qualityFilter))

  const handleUnverify = async (item: VerifiedCatalogItem) => {
    if (removePending.current) return
    const ok = await confirm({
      title: 'Stop sharing with everyone?',
      message: (
        <>
          Stop sharing <strong>{item.display_name || item.name}</strong> with everyone? It will no longer appear under Everyone.
        </>
      ),
      confirmLabel: 'Remove',
      destructive: true,
    })
    if (!ok) return
    if (removePending.current) return
    removePending.current = true; setRemoving(item.item_id)
    try { await unverifyItem(item.kind, item.item_id); refresh() }
    catch (reason) { toast(reason instanceof Error ? reason.message : 'Could not stop sharing. Retry the change.', 'error') }
    finally { removePending.current = false; setRemoving(null) }
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
            onChange={(e) => { setSearchQuery(e.target.value); setPageIndex(0) }}
            placeholder="Search shared items..."
            aria-label="Search shared items"
            className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {([['', 'All'], ['workflow', 'Workflows'], ['search_set', 'Extractions'], ['knowledge_base', 'Knowledge Bases']] as [KindFilter, string][]).map(([val, label]) => (
            <button
              key={val}
              aria-pressed={kindFilter === val}
              onClick={() => { setKindFilter(val); setPageIndex(0) }}
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
        <select
          value={qualityFilter}
          onChange={(e) => setQualityFilter(e.target.value as QualityFilter)}
          aria-label="Filter by quality"
          className="px-3 py-1 text-xs border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
        >
          <option value="">All Quality</option>
          <option value="excellent">Excellent</option>
          <option value="good">Good or better</option>
          <option value="fair">Fair or better</option>
        </select>
        <div className="flex items-center gap-1 ml-auto">
          <button
            onClick={() => window.open(exportCatalogUrl(), '_blank')}
            title="Export catalog"
            className="p-1.5 rounded hover:bg-gray-100 text-gray-500"
          >
            <Download className="h-4 w-4" />
          </button>
          <button
            onClick={() => importInputRef.current?.click()}
            title="Import catalog"
            className="p-1.5 rounded hover:bg-gray-100 text-gray-500"
          >
            <Upload className="h-4 w-4" />
          </button>
          <input
            ref={importInputRef}
            type="file"
            aria-label="Upload files"
            accept=".json"
            className="hidden"
            onChange={async (e) => {
              const f = e.target.files?.[0]
              if (!f) return
              e.target.value = ''
              try {
                const preview = await previewCatalogImport(f)
                setImportFile(f)
                setImportPreview(preview)
              } catch (err: unknown) {
                toast(err instanceof Error ? err.message : 'Failed to read file', 'error')
              }
            }}
          />
        </div>
      </div>

      {collectionError && <p role="alert" className="mb-3 text-sm text-red-800">Collection choices unavailable. <button onClick={refreshCollections} className="underline">Retry collection choices</button></p>}
      {data && data.total > 200 && <div className="mb-3 flex flex-wrap gap-3 text-sm"><span>Page {pageIndex + 1} of {Math.ceil(data.total / 200)}. Quality filtering applies to this page.</span><button disabled={pageIndex === 0} onClick={() => setPageIndex(value => value - 1)}>Previous page</button><button disabled={(pageIndex + 1) * 200 >= data.total} onClick={() => setPageIndex(value => value + 1)}>Next page</button></div>}
      {error ? <p role="alert" className="p-3 text-sm text-red-800">{error} <button onClick={refresh} className="underline">Retry catalog</button></p> : loading ? (
        <div role="status" aria-live="polite" className="text-sm text-gray-500 py-8 text-center">Loading...</div>
      ) : shown.length === 0 ? (
        <div role="status" aria-live="polite" className="text-sm text-gray-500 py-12 text-center">
          No shared items match these filters on this page.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {shown.map((item) => (
            <div
              key={item.id}
              className="border border-gray-200 rounded-lg p-4 bg-white hover:border-gray-300 transition-colors"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <ShieldCheck className="h-4 w-4 text-green-500 shrink-0" />
                    <span className="text-sm font-semibold text-gray-900 break-words">
                      {item.display_name || item.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <KindBadge kind={item.kind} />
                    <QualityContractBadge
                      status={item.last_validated_at ? 'monitored' : 'unmonitored'}
                      tier={item.quality_tier}
                      score={item.quality_score}
                      lastValidatedAt={item.last_validated_at}
                      isStale={item.last_validated_at ? (Date.now() - new Date(item.last_validated_at).getTime()) > 14 * 86400000 : false}
                      monitored={true}
                      asserted={item.quality_asserted}
                    />
                    {item.created_at && (
                      <span className="text-xs text-gray-500">
                        {new Date(item.created_at).toLocaleDateString()}
                      </span>
                    )}
                    {(item.submitted_by || item.credit || item.created_by) && (
                      <AuthorChip author={item.submitted_by || item.credit || item.created_by} label="by" />
                    )}
                  </div>
                  {item.description && (
                    <p className="text-xs text-gray-600 line-clamp-2">{item.description}</p>
                  )}
                  {item.kind === 'knowledge_base' && (item.total_sources != null || item.total_chunks != null) && (
                    <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-500">
                      {item.total_sources != null && (
                        <span>{item.total_sources} source{item.total_sources !== 1 ? 's' : ''}</span>
                      )}
                      {item.total_chunks != null && (
                        <span>{item.total_chunks.toLocaleString()} chunks</span>
                      )}
                    </div>
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
                  {item.organization_ids?.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {item.organization_ids.map(oid => (
                        <span key={oid} className="text-xs px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200 flex items-center gap-1">
                          <Tag className="h-3 w-3" />
                          {orgMap[oid] || oid}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-1 shrink-0 w-full sm:w-auto">
                  <CollectionPicker
                    itemId={item.item_id}
                    collections={collections}
                    unavailable={!!collectionError}
                    onAdded={refreshCollections}
                  />
                  <button
                    onClick={() => setEditingItem(item)}
                    className="p-1.5 rounded hover:bg-gray-100 text-gray-500"
                    title="Edit Metadata"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button
                    disabled={removing !== null}
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

      {importPreview && importFile && (
        <CatalogImportDialog
          items={importPreview}
          file={importFile}
          onClose={() => { setImportPreview(null); setImportFile(null) }}
          onImported={() => { setImportPreview(null); setImportFile(null); refresh() }}
        />
      )}
    </div>
  )
}
