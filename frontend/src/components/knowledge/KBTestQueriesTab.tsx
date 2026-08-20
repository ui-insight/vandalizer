import { useMemo, useState } from 'react'
import { Plus, Sparkles, Trash2, Bot, User, Loader2, Pencil, Upload } from 'lucide-react'
import {
  createKBTestQuery,
  updateKBTestQuery,
  deleteKBTestQuery,
  bulkDeleteKBTestQueries,
  generateKBTestQueriesAndWait,
  type KBTestQuery,
} from '../../api/knowledge'
import { GenerateTestQueriesModal } from './GenerateTestQueriesModal'
import { ImportTestQueriesModal } from './ImportTestQueriesModal'
import { useConfirm } from '../shared/useConfirm'
import { useToast } from '../../contexts/ToastContext'

interface Props {
  kbUuid: string
  kbReady: boolean
  canManage: boolean
  queries: KBTestQuery[]
  onChange: () => void
}

export type DraftShape = {
  query: string
  expected_answer: string
  expected_source_labels: string
  category: string
  notes: string
}

// Mirrors _TEST_QUERY_BULK_DELETE_MAX in backend/app/routers/knowledge.py.
export const BULK_DELETE_BATCH = 2000

/** Split ids into request-sized batches, so a selection larger than the
 * server's cap deletes instead of being rejected whole. */
export function chunkForBulkDelete(uuids: string[], size = BULK_DELETE_BATCH): string[][] {
  const batches: string[][] = []
  for (let i = 0; i < uuids.length; i += size) batches.push(uuids.slice(i, i + size))
  return batches
}

export const EMPTY_DRAFT: DraftShape = {
  query: '',
  expected_answer: '',
  expected_source_labels: '',
  category: 'factual',
  notes: '',
}

const CATEGORIES = ['factual', 'summary', 'enumeration', 'boundary']

/** Which slice of the test set the list is showing. Imported sets and LLM
 * generation runs both land in the same list, so authorship is the axis
 * evaluators actually prune along. */
type SourceFilter = 'all' | 'user' | 'auto'

const FILTER_LABELS: Record<SourceFilter, string> = {
  all: 'All',
  user: 'User-authored',
  auto: 'Auto-generated',
}

function matchesFilter(q: KBTestQuery, filter: SourceFilter): boolean {
  if (filter === 'auto') return q.auto_generated
  if (filter === 'user') return !q.auto_generated
  return true
}

/** Convert a saved query into the editable draft shape (comma-joined labels,
 * nulls coerced to empty strings). Single-sourced so the Test Queries tab and
 * the Autovalidate wizard preview edit queries identically. */
export function queryToDraft(q: KBTestQuery): DraftShape {
  return {
    query: q.query,
    expected_answer: q.expected_answer ?? '',
    expected_source_labels: q.expected_source_labels.join(', '),
    category: q.category ?? 'factual',
    notes: q.notes ?? '',
  }
}

/** Convert an editable draft back into a PATCH payload for updateKBTestQuery. */
export function draftToUpdatePayload(draft: DraftShape) {
  return {
    query: draft.query.trim(),
    expected_answer: draft.expected_answer.trim() || null,
    expected_source_labels: draft.expected_source_labels
      .split(',').map(s => s.trim()).filter(Boolean),
    category: draft.category,
    notes: draft.notes.trim() || null,
  }
}

export function KBTestQueriesTab({ kbUuid, kbReady, canManage, queries, onChange }: Props) {
  const confirm = useConfirm()
  const { toast } = useToast()
  const [showGen, setShowGen] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [adding, setAdding] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [draft, setDraft] = useState<DraftShape>(EMPTY_DRAFT)
  // When set, the matching query card renders an inline edit form instead of
  // its read-only view. `editDraft` holds the in-progress edits.
  const [editingUuid, setEditingUuid] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState<DraftShape>(EMPTY_DRAFT)
  const [saving, setSaving] = useState(false)
  const [filter, setFilter] = useState<SourceFilter>('all')
  // Selection is keyed by uuid and kept across filter changes, so an
  // evaluator can gather a batch from more than one slice before deleting.
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const autoCount = useMemo(() => queries.filter(q => q.auto_generated).length, [queries])
  const userCount = queries.length - autoCount
  const visible = useMemo(
    () => queries.filter(q => matchesFilter(q, filter)),
    [queries, filter],
  )
  // Only queries still on screen count toward the selection UI — a stale id
  // (deleted elsewhere, or filtered out) must not make the header claim a
  // selection the user cannot see.
  const selectedVisible = useMemo(
    () => visible.filter(q => selected.has(q.uuid)),
    [visible, selected],
  )
  const selectedCount = useMemo(
    () => queries.filter(q => selected.has(q.uuid)).length,
    [queries, selected],
  )
  const allVisibleSelected = visible.length > 0 && selectedVisible.length === visible.length

  const toggleSelected = (uuid: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(uuid)) next.delete(uuid)
      else next.add(uuid)
      return next
    })
  }

  const toggleSelectAllVisible = () => {
    setSelected(prev => {
      const next = new Set(prev)
      if (allVisibleSelected) visible.forEach(q => next.delete(q.uuid))
      else visible.forEach(q => next.add(q.uuid))
      return next
    })
  }

  // Writing rows into a slice the current filter hides reads as a silent
  // failure — generation has no success toast, so the only sign it worked is
  // a counter ticking up in the filter bar, which invites a re-run and a
  // duplicate batch. Any operation that adds rows returns the list to 'all'.
  const revealNewRows = () => setFilter('all')

  const handleAdd = async () => {
    if (!draft.query.trim()) return
    setAdding(true)
    try {
      await createKBTestQuery(kbUuid, {
        query: draft.query.trim(),
        expected_answer: draft.expected_answer.trim() || undefined,
        expected_source_labels: draft.expected_source_labels
          .split(',').map(s => s.trim()).filter(Boolean),
        category: draft.category,
        notes: draft.notes.trim() || undefined,
      })
      setDraft(EMPTY_DRAFT)
      setShowAdd(false)
      revealNewRows()
      await onChange()
    } finally {
      setAdding(false)
    }
  }

  const startEdit = (q: KBTestQuery) => {
    setShowAdd(false)
    setEditingUuid(q.uuid)
    setEditDraft(queryToDraft(q))
  }

  const handleUpdate = async () => {
    if (!editingUuid || !editDraft.query.trim()) return
    setSaving(true)
    try {
      await updateKBTestQuery(kbUuid, editingUuid, draftToUpdatePayload(editDraft))
      setEditingUuid(null)
      await onChange()
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (q: KBTestQuery) => {
    const ok = await confirm({
      title: 'Delete test query',
      message: `Delete this test query?\n\n"${q.query}"`,
      destructive: true,
    })
    if (!ok) return
    await deleteKBTestQuery(kbUuid, q.uuid)
    setSelected(prev => {
      if (!prev.has(q.uuid)) return prev
      const next = new Set(prev)
      next.delete(q.uuid)
      return next
    })
    await onChange()
  }

  const handleDeleteSelected = async () => {
    const uuids = queries.filter(q => selected.has(q.uuid)).map(q => q.uuid)
    if (uuids.length === 0) return
    const ok = await confirm({
      title: `Delete ${uuids.length} test ${uuids.length === 1 ? 'query' : 'queries'}`,
      message:
        `Delete ${uuids.length} selected test ${uuids.length === 1 ? 'query' : 'queries'}? ` +
        'This cannot be undone. Past runs keep the scores and answers they ' +
        'recorded, but a validation run re-exported afterwards will have a ' +
        'blank expected answer for any question deleted here.',
      destructive: true,
    })
    if (!ok) return
    setBulkDeleting(true)
    try {
      // The endpoint caps a batch, and "hundreds, imported repeatedly" is the
      // population this feature exists for — one generation run from crossing
      // it. Sending the lot would 400 the whole thing and delete nothing,
      // leaving unchecking rows by hand as the only way forward.
      let deleted = 0
      for (const batch of chunkForBulkDelete(uuids)) {
        deleted += (await bulkDeleteKBTestQueries(kbUuid, batch)).deleted
      }
      setSelected(new Set())
      setEditingUuid(null)
      await onChange()
      toast(`Deleted ${deleted} test ${deleted === 1 ? 'query' : 'queries'}.`, 'success')
    } catch (e) {
      toast(`Delete failed: ${(e as Error).message}`, 'error')
    } finally {
      setBulkDeleting(false)
    }
  }

  const handleGenerate = async (coverage: 'quick' | 'standard' | 'exhaustive') => {
    setGenerating(true)
    setShowGen(false)
    try {
      // Runs on a background worker and polls for completion — the inline LLM
      // call could exceed the proxy's gateway timeout and 502 on larger KBs.
      await generateKBTestQueriesAndWait(kbUuid, { coverage })
      revealNewRows()
      await onChange()
    } catch (e) {
      toast(`Generation failed: ${(e as Error).message}`, 'error')
    } finally {
      setGenerating(false)
    }
  }

  const disabledReason = !kbReady ? 'KB is still building' : !canManage ? 'You cannot manage this KB' : null

  return (
    <div>
      {/* Action bar */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
        <button
          type="button"
          onClick={() => setShowAdd(v => !v)}
          disabled={!!disabledReason}
          style={btn(!disabledReason)}
        >
          <Plus size={12} aria-hidden="true" />
          Add manually
        </button>
        <button
          type="button"
          onClick={() => setShowImport(true)}
          disabled={!!disabledReason}
          style={btn(!disabledReason, '#0ea5e9')}
          title={disabledReason || 'Bulk-import test queries from a CSV or Excel file'}
        >
          <Upload size={12} aria-hidden="true" />
          Import CSV/Excel
        </button>
        <button
          type="button"
          onClick={() => setShowGen(true)}
          disabled={!!disabledReason || generating}
          style={btn(!disabledReason && !generating, '#7c3aed')}
          title={disabledReason || 'Auto-generate test queries from KB content'}
        >
          {generating ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" /> : <Sparkles size={12} aria-hidden="true" />}
          {generating ? 'Generating…' : 'Auto-generate (LLM)'}
        </button>
      </div>

      {/* Add form */}
      {showAdd && (
        <div style={{
          padding: 10, marginBottom: 10,
          backgroundColor: '#252525', border: '1px solid #333', borderRadius: 6,
          display: 'flex', flexDirection: 'column', gap: 8,
        }}>
          <QueryFormFields draft={draft} onChange={setDraft} />
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" onClick={handleAdd} disabled={adding || !draft.query.trim()} style={btn(!adding && !!draft.query.trim(), '#15803d')}>
              {adding ? 'Adding…' : 'Save'}
            </button>
            <button type="button" onClick={() => setShowAdd(false)} style={btn(true)}>Cancel</button>
          </div>
        </div>
      )}

      {/* Filter + bulk-selection bar. Large test sets are mostly imported or
          auto-generated, so pruning them is the common case, not the rare one. */}
      {queries.length > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
          padding: '6px 8px', marginBottom: 8,
          backgroundColor: '#222', border: '1px solid #333', borderRadius: 6,
        }}>
          {canManage && (
            <label style={{
              display: 'inline-flex', alignItems: 'center', gap: 5,
              fontSize: 11, color: '#bbb', cursor: visible.length ? 'pointer' : 'default',
            }}>
              <input
                type="checkbox"
                checked={allVisibleSelected}
                ref={el => { if (el) el.indeterminate = selectedVisible.length > 0 && !allVisibleSelected }}
                onChange={toggleSelectAllVisible}
                disabled={visible.length === 0}
                aria-label={`Select all ${FILTER_LABELS[filter].toLowerCase()} test queries`}
              />
              Select all{filter === 'all' ? '' : ` ${FILTER_LABELS[filter].toLowerCase()}`}
            </label>
          )}

          <div role="group" aria-label="Filter test queries" style={{ display: 'flex', gap: 4 }}>
            {(['all', 'user', 'auto'] as SourceFilter[]).map(f => {
              const count = f === 'all' ? queries.length : f === 'user' ? userCount : autoCount
              const active = filter === f
              return (
                <button
                  key={f}
                  type="button"
                  onClick={() => setFilter(f)}
                  aria-pressed={active}
                  style={{
                    padding: '3px 8px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
                    color: active ? '#e5e5e5' : '#888',
                    backgroundColor: active ? '#333' : 'transparent',
                    border: `1px solid ${active ? '#4a4a4a' : 'transparent'}`,
                    borderRadius: 5, cursor: 'pointer',
                  }}
                >
                  {FILTER_LABELS[f]} ({count})
                </button>
              )
            })}
          </div>

          {canManage && selectedCount > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
              <span style={{ fontSize: 11, color: '#888' }} role="status">
                {selectedCount} selected
              </span>
              <button
                type="button"
                onClick={() => setSelected(new Set())}
                style={{
                  background: 'transparent', border: 'none', padding: 0,
                  fontSize: 11, fontFamily: 'inherit', color: '#888',
                  textDecoration: 'underline', cursor: 'pointer',
                }}
              >
                Clear
              </button>
              <button
                type="button"
                onClick={handleDeleteSelected}
                disabled={bulkDeleting}
                style={btn(!bulkDeleting, '#dc2626')}
              >
                {bulkDeleting
                  ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" />
                  : <Trash2 size={12} aria-hidden="true" />}
                {bulkDeleting ? 'Deleting…' : `Delete selected (${selectedCount})`}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Queries list */}
      {queries.length === 0 ? (
        <div role="status" style={{ fontSize: 12, color: '#888', padding: '20px 0', textAlign: 'center' }}>
          No test queries yet. Add some manually or auto-generate from KB content.
        </div>
      ) : visible.length === 0 ? (
        <div role="status" style={{ fontSize: 12, color: '#888', padding: '20px 0', textAlign: 'center' }}>
          No {FILTER_LABELS[filter].toLowerCase()} test queries.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {visible.map(q => (
            <div
              key={q.uuid}
              style={{
                padding: 10,
                backgroundColor: selected.has(q.uuid) ? '#2b3140' : '#262626',
                border: `1px solid ${selected.has(q.uuid) ? '#3b82f6' : '#333'}`,
                borderRadius: 6,
              }}
            >
              {editingUuid === q.uuid ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <QueryFormFields draft={editDraft} onChange={setEditDraft} />
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button type="button" onClick={handleUpdate} disabled={saving || !editDraft.query.trim()} style={btn(!saving && !!editDraft.query.trim(), '#15803d')}>
                      {saving ? 'Saving…' : 'Save'}
                    </button>
                    <button type="button" onClick={() => setEditingUuid(null)} style={btn(true)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                  {canManage && (
                    <input
                      type="checkbox"
                      checked={selected.has(q.uuid)}
                      onChange={() => toggleSelected(q.uuid)}
                      aria-label={`Select test query: ${q.query}`}
                      style={{ flexShrink: 0, marginTop: 2, cursor: 'pointer' }}
                    />
                  )}
                  {q.auto_generated ? (
                    <Bot size={13} style={{ color: '#7c3aed', flexShrink: 0, marginTop: 2 }} aria-label="Auto-generated" />
                  ) : (
                    <User size={13} style={{ color: '#888', flexShrink: 0, marginTop: 2 }} aria-label="User-authored" />
                  )}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, color: '#e5e5e5', marginBottom: 4 }}>{q.query}</div>
                    {q.expected_answer && (
                      <div style={{ fontSize: 11, color: '#888', marginBottom: 2 }}>
                        <span style={{ color: '#666' }}>Expected: </span>{q.expected_answer}
                      </div>
                    )}
                    {q.notes && (
                      <div style={{ fontSize: 11, color: '#888', marginBottom: 2, fontStyle: 'italic' }}>
                        <span style={{ color: '#666', fontStyle: 'normal' }}>Notes: </span>{q.notes}
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: 8, fontSize: 10, color: '#666', marginTop: 4, flexWrap: 'wrap' }}>
                      {q.external_id && <span>· ID: {q.external_id}</span>}
                      {q.category && <span>· {q.category}</span>}
                      {q.expected_source_labels.length > 0 && (
                        <span>· sources: {q.expected_source_labels.join(', ')}</span>
                      )}
                      {q.last_judged_score != null && (
                        <span style={{ color: scoreColor(q.last_judged_score) }}>
                          · last score: {(q.last_judged_score * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                  </div>
                  {canManage && (
                    <div style={{ display: 'flex', gap: 2, flexShrink: 0 }}>
                      <button
                        type="button"
                        onClick={() => startEdit(q)}
                        style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, color: '#666' }}
                        title="Edit"
                        aria-label="Edit test query"
                      >
                        <Pencil size={12} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(q)}
                        style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, color: '#666' }}
                        title="Delete"
                        aria-label="Delete test query"
                      >
                        <Trash2 size={12} aria-hidden="true" />
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {showGen && (
        <GenerateTestQueriesModal
          onConfirm={handleGenerate}
          onClose={() => setShowGen(false)}
        />
      )}

      {showImport && (
        <ImportTestQueriesModal
          kbUuid={kbUuid}
          onImported={async () => { revealNewRows(); await onChange() }}
          onClose={() => setShowImport(false)}
        />
      )}
    </div>
  )
}

/** Shared query/expected-answer/labels/category fields used by both the
 * "add" form and a card's inline "edit" form. */
export function QueryFormFields({ draft, onChange }: { draft: DraftShape; onChange: (d: DraftShape) => void }) {
  // Preserve an unusual category (e.g. from an auto-generated query) by
  // surfacing it as an extra option rather than silently dropping it.
  const categories = CATEGORIES.includes(draft.category)
    ? CATEGORIES
    : [draft.category, ...CATEGORIES]
  return (
    <>
      <input
        aria-label="Query"
        placeholder="Query…"
        value={draft.query}
        onChange={e => onChange({ ...draft, query: e.target.value })}
        style={input()}
      />
      <textarea
        aria-label="Expected answer"
        placeholder="Expected answer (the canonical correct answer the LLM judge will compare against)"
        value={draft.expected_answer}
        onChange={e => onChange({ ...draft, expected_answer: e.target.value })}
        style={{ ...input(), minHeight: 60, resize: 'vertical' as const }}
      />
      <input
        aria-label="Expected source labels"
        placeholder="Expected source labels (comma-separated, optional)"
        value={draft.expected_source_labels}
        onChange={e => onChange({ ...draft, expected_source_labels: e.target.value })}
        style={input()}
      />
      <select
        aria-label="Category"
        value={draft.category}
        onChange={e => onChange({ ...draft, category: e.target.value })}
        style={input()}
      >
        {categories.map(c => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>
      <input
        aria-label="Notes"
        placeholder="Notes (optional — rationale, provenance, caveats)"
        value={draft.notes}
        onChange={e => onChange({ ...draft, notes: e.target.value })}
        style={input()}
      />
    </>
  )
}

function scoreColor(score: number) {
  if (score >= 0.7) return '#22c55e'
  if (score >= 0.4) return '#f59e0b'
  return '#ef4444'
}

function btn(enabled: boolean, color?: string): React.CSSProperties {
  return {
    display: 'inline-flex', alignItems: 'center', gap: 4,
    padding: '4px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
    color: enabled ? '#e5e5e5' : '#555',
    backgroundColor: color ? `${color}1a` : '#2a2a2a',
    border: `1px solid ${color ? `${color}55` : '#3a3a3a'}`,
    borderRadius: 5,
    cursor: enabled ? 'pointer' : 'not-allowed',
    opacity: enabled ? 1 : 0.5,
  }
}

function input(): React.CSSProperties {
  return {
    background: '#1a1a1a', color: '#e5e5e5',
    border: '1px solid #333', borderRadius: 4,
    padding: '6px 8px', fontSize: 12, fontFamily: 'inherit',
  }
}
