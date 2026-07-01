import { useState } from 'react'
import { Plus, Sparkles, Trash2, Bot, User, Loader2, Pencil } from 'lucide-react'
import {
  createKBTestQuery,
  updateKBTestQuery,
  deleteKBTestQuery,
  generateKBTestQueriesAndWait,
  type KBTestQuery,
} from '../../api/knowledge'
import { GenerateTestQueriesModal } from './GenerateTestQueriesModal'
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
}

export const EMPTY_DRAFT: DraftShape = {
  query: '',
  expected_answer: '',
  expected_source_labels: '',
  category: 'factual',
}

const CATEGORIES = ['factual', 'summary', 'enumeration', 'boundary']

/** Convert a saved query into the editable draft shape (comma-joined labels,
 * nulls coerced to empty strings). Single-sourced so the Test Queries tab and
 * the Autovalidate wizard preview edit queries identically. */
export function queryToDraft(q: KBTestQuery): DraftShape {
  return {
    query: q.query,
    expected_answer: q.expected_answer ?? '',
    expected_source_labels: q.expected_source_labels.join(', '),
    category: q.category ?? 'factual',
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
  }
}

export function KBTestQueriesTab({ kbUuid, kbReady, canManage, queries, onChange }: Props) {
  const confirm = useConfirm()
  const { toast } = useToast()
  const [showGen, setShowGen] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [adding, setAdding] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [draft, setDraft] = useState<DraftShape>(EMPTY_DRAFT)
  // When set, the matching query card renders an inline edit form instead of
  // its read-only view. `editDraft` holds the in-progress edits.
  const [editingUuid, setEditingUuid] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState<DraftShape>(EMPTY_DRAFT)
  const [saving, setSaving] = useState(false)

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
      })
      setDraft(EMPTY_DRAFT)
      setShowAdd(false)
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
    await onChange()
  }

  const handleGenerate = async (coverage: 'quick' | 'standard' | 'exhaustive') => {
    setGenerating(true)
    setShowGen(false)
    try {
      // Runs on a background worker and polls for completion — the inline LLM
      // call could exceed the proxy's gateway timeout and 502 on larger KBs.
      await generateKBTestQueriesAndWait(kbUuid, { coverage })
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

      {/* Queries list */}
      {queries.length === 0 ? (
        <div role="status" style={{ fontSize: 12, color: '#888', padding: '20px 0', textAlign: 'center' }}>
          No test queries yet. Add some manually or auto-generate from KB content.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {queries.map(q => (
            <div
              key={q.uuid}
              style={{
                padding: 10, backgroundColor: '#262626',
                border: '1px solid #333', borderRadius: 6,
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
                    <div style={{ display: 'flex', gap: 8, fontSize: 10, color: '#666', marginTop: 4, flexWrap: 'wrap' }}>
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
