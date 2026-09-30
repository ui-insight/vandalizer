import { useMemo, useState } from 'react'
import { Plus, Sparkles, Trash2, Bot, User, Loader2, Pencil, Upload, Play, Search } from 'lucide-react'
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
  /** Hand the selected queries to the Run tab, which shows their count and
   *  category mix before the user starts the (smoke-test) run. Absent when
   *  running is not offered. */
  onRunSelected?: (uuids: string[]) => void
  /** True while any validation run is in flight — disables Run selected. */
  running?: boolean
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

/** Free-text narrowing over the columns a reviewer tracks a question by:
 * ID (imported, or the generated `PREFIX-AUTO-Q001`), question, expected
 * answer, category, source labels and notes. Case-insensitive substring. */
export function matchesSearch(q: KBTestQuery, term: string): boolean {
  const needle = term.trim().toLowerCase()
  if (!needle) return true
  const haystack = [
    q.external_id, q.query, q.expected_answer, q.category, q.notes,
    ...q.expected_source_labels,
  ]
  return haystack.some(v => typeof v === 'string' && v.toLowerCase().includes(needle))
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

export function KBTestQueriesTab({
  kbUuid, kbReady, canManage, queries, onChange, onRunSelected, running = false,
}: Props) {
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
  const [search, setSearch] = useState('')
  const [displayLimit, setDisplayLimit] = useState(50)
  // Selection is keyed by uuid and kept across filter changes, so an
  // evaluator can gather a batch from more than one slice before deleting.
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkDeleting, setBulkDeleting] = useState(false)
  const [deletingUuid, setDeletingUuid] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const busy = adding || saving || bulkDeleting || deletingUuid !== null

  const autoCount = useMemo(() => queries.filter(q => q.auto_generated).length, [queries])
  const userCount = queries.length - autoCount
  const visible = useMemo(
    () => queries.filter(q => matchesFilter(q, filter) && matchesSearch(q, search)),
    [queries, filter, search],
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
  const revealNewRows = () => { setFilter('all'); setSearch(''); setDisplayLimit(50) }

  const handleAdd = async () => {
    if (!draft.query.trim() || busy) return
    setAdding(true)
    setActionError(null)
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
      toast('Test question added.', 'success')
    } catch (e) {
      setActionError(`Could not add this question: ${(e as Error).message}. Your draft is preserved; retry Save.`)
    } finally {
      setAdding(false)
    }
  }

  const startEdit = (q: KBTestQuery) => {
    setActionError(null)
    setShowAdd(false)
    setEditingUuid(q.uuid)
    setEditDraft(queryToDraft(q))
  }

  const handleUpdate = async () => {
    if (!editingUuid || !editDraft.query.trim() || busy) return
    setSaving(true)
    setActionError(null)
    try {
      await updateKBTestQuery(kbUuid, editingUuid, draftToUpdatePayload(editDraft))
      setEditingUuid(null)
      await onChange()
      toast('Test question saved.', 'success')
    } catch (e) {
      setActionError(`Could not save this question: ${(e as Error).message}. Your edits are preserved; retry Save.`)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (q: KBTestQuery) => {
    if (busy) return
    const ok = await confirm({
      title: 'Delete test query',
      message: `Delete this test query?\n\n"${q.query}"`,
      destructive: true,
    })
    if (!ok) return
    setDeletingUuid(q.uuid)
    setActionError(null)
    try {
      await deleteKBTestQuery(kbUuid, q.uuid)
      setSelected(prev => { const next = new Set(prev); next.delete(q.uuid); return next })
      await onChange()
      toast('Test question deleted.', 'success')
    } catch (e) {
      setActionError(`Could not delete “${q.query}”: ${(e as Error).message}. Your selection is preserved.`)
    } finally { setDeletingUuid(null) }
  }

  const handleRunSelected = () => {
    const uuids = queries.filter(q => selected.has(q.uuid)).map(q => q.uuid)
    if (uuids.length === 0 || !onRunSelected) return
    onRunSelected(uuids)
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
    setActionError(null)
    let deleted = 0
    try {
      // The endpoint caps a batch, and "hundreds, imported repeatedly" is the
      // population this feature exists for — one generation run from crossing
      // it. Sending the lot would 400 the whole thing and delete nothing,
      // leaving unchecking rows by hand as the only way forward.
      for (const batch of chunkForBulkDelete(uuids)) {
        deleted += (await bulkDeleteKBTestQueries(kbUuid, batch)).deleted
        setSelected(prev => { const next = new Set(prev); batch.forEach(id => next.delete(id)); return next })
      }
      setSelected(new Set())
      setEditingUuid(null)
      await onChange()
      toast(`Deleted ${deleted} test ${deleted === 1 ? 'query' : 'queries'}.`, 'success')
    } catch (e) {
      await onChange()
      setActionError(`Deleted ${deleted} questions before deletion stopped: ${(e as Error).message}. Remaining questions stay selected; retry Delete selected.`)
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

  const disabledReason = !kbReady ? 'KB is still building' : !canManage ? 'You cannot manage this KB' : busy ? 'A question change is in progress' : null

  return (
    <div>
      {actionError && <div role="alert" style={{ color: 'var(--workspace-danger)', fontSize: 13, lineHeight: 1.6, marginBottom: 12, overflowWrap: 'anywhere' }}>{actionError}</div>}
      {/* Action bar */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
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
          style={btn(!disabledReason, 'var(--workspace-info)')}
          title={disabledReason || 'Bulk-import test queries from a CSV or Excel file'}
        >
          <Upload size={12} aria-hidden="true" />
          Import CSV/Excel
        </button>
        <button
          type="button"
          onClick={() => setShowGen(true)}
          disabled={!!disabledReason || generating}
          style={btn(!disabledReason && !generating, 'var(--workspace-info)')}
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
          backgroundColor: 'var(--workspace-surface)', border: '1px solid var(--workspace-border)', borderRadius: 6,
          display: 'flex', flexDirection: 'column', gap: 8,
        }}>
          <QueryFormFields draft={draft} onChange={setDraft} disabled={adding} />
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" onClick={handleAdd} disabled={adding || !draft.query.trim()} style={btn(!adding && !!draft.query.trim(), '#15803d')}>
              {adding ? 'Adding…' : 'Save'}
            </button>
            <button type="button" onClick={() => setShowAdd(false)} disabled={adding} style={btn(!adding)}>Cancel</button>
          </div>
        </div>
      )}

      {/* Filter + bulk-selection bar. Large test sets are mostly imported or
          auto-generated, so pruning them is the common case, not the rare one. */}
      {queries.length > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
          padding: '6px 8px', marginBottom: 8,
          backgroundColor: 'var(--workspace-surface)', border: '1px solid var(--workspace-border)', borderRadius: 6,
        }}>
          {canManage && (
            <label style={{
              display: 'inline-flex', alignItems: 'center', gap: 5,
              fontSize: 12, color: 'var(--workspace-muted)', cursor: visible.length ? 'pointer' : 'default',
            }}>
              <input
                type="checkbox"
                checked={allVisibleSelected}
                ref={el => { if (el) el.indeterminate = selectedVisible.length > 0 && !allVisibleSelected }}
                onChange={toggleSelectAllVisible}
                disabled={visible.length === 0}
                aria-label={`Select all ${FILTER_LABELS[filter].toLowerCase()} test queries`}
              />
              Select all {visible.length}{filter === 'all' ? '' : ` ${FILTER_LABELS[filter].toLowerCase()}`}
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
                  onClick={() => { setFilter(f); setDisplayLimit(50) }}
                  aria-pressed={active}
                  style={{
                    padding: '3px 8px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                    color: active ? 'var(--workspace-text)' : 'var(--workspace-muted)',
                    backgroundColor: active ? 'var(--workspace-surface)' : 'transparent',
                    border: `1px solid ${active ? 'var(--workspace-border)' : 'transparent'}`,
                    borderRadius: 5, cursor: 'pointer',
                  }}
                >
                  {FILTER_LABELS[f]} ({count})
                </button>
              )
            })}
          </div>

          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, minWidth: 0 }}>
            <Search size={12} style={{ color: 'var(--workspace-muted)', flexShrink: 0 }} aria-hidden="true" />
            <input
              type="search"
              value={search}
              onChange={e => { setSearch(e.target.value); setDisplayLimit(50) }}
              placeholder="Search ID, question, source…"
              aria-label="Search test queries by ID, question, category, source or notes"
              style={{
                width: 190, padding: '3px 6px', fontSize: 12, fontFamily: 'inherit',
                color: 'var(--workspace-text)', backgroundColor: 'var(--workspace-canvas)',
                border: '1px solid var(--workspace-border)', borderRadius: 5,
              }}
            />
          </label>

          {canManage && selectedCount > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto', flexWrap: 'wrap' }}>
              <span style={{ fontSize: 12, color: 'var(--workspace-muted)' }} role="status">
                {selectedCount} selected
              </span>
              <button
                type="button"
                onClick={() => setSelected(new Set())}
                style={{
                  background: 'transparent', border: 'none', padding: 0,
                  fontSize: 12, fontFamily: 'inherit', color: 'var(--workspace-muted)',
                  textDecoration: 'underline', cursor: 'pointer',
                }}
              >
                Clear
              </button>
              {onRunSelected && (
                <button
                  type="button"
                  onClick={handleRunSelected}
                  disabled={!kbReady || running || bulkDeleting}
                  title={
                    'Open Run now with only the selected questions, to review the count and categories ' +
                    'before starting. The run appears in History, where its export holds just these ' +
                    "questions. It is a smoke test and does not change the KB's quality score."
                  }
                  style={btn(kbReady && !running && !bulkDeleting, '#2563eb')}
                >
                  {running
                    ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" />
                    : <Play size={12} aria-hidden="true" />}
                  {running ? 'Running…' : `Run selected (${selectedCount})`}
                </button>
              )}
              <button
                type="button"
                onClick={handleDeleteSelected}
                disabled={busy}
                style={btn(!bulkDeleting, 'var(--workspace-danger)')}
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
        <div role="status" style={{ fontSize: 12, color: 'var(--workspace-muted)', padding: '20px 0', textAlign: 'center' }}>
          No test queries yet. Add some manually or auto-generate from KB content.
        </div>
      ) : visible.length === 0 ? (
        <div role="status" style={{ fontSize: 12, color: 'var(--workspace-muted)', padding: '20px 0', textAlign: 'center' }}>
          No {FILTER_LABELS[filter].toLowerCase()} test queries{search.trim() ? ` match “${search.trim()}”` : ''}.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {visible.length > 50 && <p style={{ fontSize: 12, color: 'var(--workspace-muted)', margin: '4px 0' }}>Showing {Math.min(displayLimit, visible.length)} of {visible.length} matching questions. Select all includes every matching question.</p>}
          {visible.slice(0, displayLimit).map(q => (
            <div
              key={q.uuid}
              style={{
                padding: 10,
                backgroundColor: selected.has(q.uuid) ? 'var(--workspace-info-surface)' : 'var(--workspace-surface)',
                border: `1px solid ${selected.has(q.uuid) ? '#3b82f6' : 'var(--workspace-border)'}`,
                borderRadius: 6,
              }}
            >
              {editingUuid === q.uuid ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <QueryFormFields draft={editDraft} onChange={setEditDraft} disabled={saving} />
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button type="button" onClick={handleUpdate} disabled={saving || !editDraft.query.trim()} style={btn(!saving && !!editDraft.query.trim(), '#15803d')}>
                      {saving ? 'Saving…' : 'Save'}
                    </button>
                    <button type="button" onClick={() => setEditingUuid(null)} disabled={saving} style={btn(!saving)}>Cancel</button>
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
                    <Bot size={13} style={{ color: 'var(--workspace-info)', flexShrink: 0, marginTop: 2 }} aria-label="Auto-generated" />
                  ) : (
                    <User size={13} style={{ color: 'var(--workspace-muted)', flexShrink: 0, marginTop: 2 }} aria-label="User-authored" />
                  )}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, color: 'var(--workspace-text)', marginBottom: 4 }}>
                      {q.external_id && (
                        <code
                          title="Question ID — assigned once and kept across validation runs and exports; regenerating creates new IDs"
                          style={{
                            fontSize: 12, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                            color: 'var(--workspace-info)', backgroundColor: 'var(--workspace-info-surface)',
                            padding: '1px 5px', borderRadius: 4, marginRight: 8, whiteSpace: 'nowrap',
                          }}
                        >
                          {q.external_id}
                        </code>
                      )}
                      {q.query}
                    </div>
                    {q.expected_answer && (
                      <div style={{ fontSize: 12, color: 'var(--workspace-muted)', marginBottom: 2 }}>
                        <span style={{ color: 'var(--workspace-muted)' }}>Expected: </span>{q.expected_answer}
                      </div>
                    )}
                    {q.notes && (
                      <div style={{ fontSize: 12, color: 'var(--workspace-muted)', marginBottom: 2, fontStyle: 'italic' }}>
                        <span style={{ color: 'var(--workspace-muted)', fontStyle: 'normal' }}>Notes: </span>{q.notes}
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: 8, fontSize: 12, color: 'var(--workspace-muted)', marginTop: 4, flexWrap: 'wrap' }}>
                      {q.category && <span>· {q.category}</span>}
                      {q.import_batch_label && (
                        <span title={q.import_batch_at ? `Imported ${new Date(q.import_batch_at).toLocaleString()}` : undefined}>
                          · imported from {q.import_batch_label}
                        </span>
                      )}
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
                        disabled={busy}
                        style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, color: 'var(--workspace-muted)' }}
                        title="Edit"
                        aria-label="Edit test query"
                      >
                        <Pencil size={12} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(q)}
                        disabled={busy}
                        style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, color: 'var(--workspace-muted)' }}
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
          {visible.length > displayLimit && <button type="button" onClick={() => setDisplayLimit(n => n + 50)} style={btn(true)}>Show {Math.min(50, visible.length - displayLimit)} more questions</button>}
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
export function QueryFormFields({ draft, onChange, disabled = false }: { draft: DraftShape; onChange: (d: DraftShape) => void; disabled?: boolean }) {
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
        disabled={disabled}
        value={draft.query}
        onChange={e => onChange({ ...draft, query: e.target.value })}
        style={input()}
      />
      <textarea
        aria-label="Expected answer"
        placeholder="Expected answer (the canonical correct answer the LLM judge will compare against)"
        disabled={disabled}
        value={draft.expected_answer}
        onChange={e => onChange({ ...draft, expected_answer: e.target.value })}
        style={{ ...input(), minHeight: 60, resize: 'vertical' as const }}
      />
      <input
        aria-label="Expected source labels"
        placeholder="Expected source labels (comma-separated, optional)"
        disabled={disabled}
        value={draft.expected_source_labels}
        onChange={e => onChange({ ...draft, expected_source_labels: e.target.value })}
        style={input()}
      />
      <select
        aria-label="Category"
        disabled={disabled}
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
        disabled={disabled}
        value={draft.notes}
        onChange={e => onChange({ ...draft, notes: e.target.value })}
        style={input()}
      />
    </>
  )
}

function scoreColor(score: number) {
  if (score >= 0.7) return 'var(--workspace-success)'
  if (score >= 0.4) return 'var(--workspace-warning)'
  return 'var(--workspace-danger)'
}

function btn(enabled: boolean, color?: string): React.CSSProperties {
  return {
    display: 'inline-flex', alignItems: 'center', gap: 4,
    padding: '4px 10px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
    color: enabled ? 'var(--workspace-text)' : 'var(--workspace-muted)',
    backgroundColor: color ? `color-mix(in srgb, ${color} 10.2%, transparent)` : 'var(--workspace-surface)',
    border: `1px solid ${color ? `color-mix(in srgb, ${color} 33.33%, transparent)` : 'var(--workspace-border)'}`,
    borderRadius: 5,
    cursor: enabled ? 'pointer' : 'not-allowed',
    opacity: enabled ? 1 : 0.5,
  }
}

function input(): React.CSSProperties {
  return {
    background: 'var(--workspace-canvas)', color: 'var(--workspace-text)',
    border: '1px solid var(--workspace-border)', borderRadius: 4,
    padding: '6px 8px', fontSize: 12, fontFamily: 'inherit',
  }
}
