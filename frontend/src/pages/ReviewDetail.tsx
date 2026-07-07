import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from '@tanstack/react-router'
import { ArrowLeft, CheckCircle, XCircle, FileText, Pencil, RotateCcw } from 'lucide-react'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { getReview, approveReview, rejectReview } from '../api/reviews'
import type { ReviewDetail, ArtifactKind } from '../api/reviews'
import { relativeTime } from '../utils/time'

function unwrapArtifact(value: ReviewDetail['data_for_review']): unknown {
  if (value && typeof value === 'object' && 'value' in value && Object.keys(value).length === 1) {
    return (value as { value: unknown }).value
  }
  return value
}

// ---------------------------------------------------------------------------
// Per-kind renderers
// ---------------------------------------------------------------------------

function TextArtifact({ data, editing, value, onChange }: {
  data: unknown; editing: boolean; value: string; onChange: (v: string) => void
}) {
  if (editing) {
    return (
      <textarea
        value={value}
        onChange={e => onChange(e.target.value)}
        rows={Math.max(8, value.split('\n').length + 2)}
        style={{
          width: '100%', padding: '10px 12px', fontSize: 13, fontFamily: 'inherit',
          border: '1px solid #d1d5db', borderRadius: 6, resize: 'vertical', boxSizing: 'border-box',
        }}
      />
    )
  }
  const text = typeof data === 'string' ? data : String(data ?? '')
  return (
    <pre style={{
      whiteSpace: 'pre-wrap', wordBreak: 'break-word',
      backgroundColor: '#f9fafb', border: '1px solid #e5e7eb',
      borderRadius: 6, padding: 12, fontSize: 13, color: '#111827',
      maxHeight: 480, overflowY: 'auto',
    }}>
      {text}
    </pre>
  )
}

function MarkdownArtifact({ data, editing, value, onChange }: {
  data: unknown; editing: boolean; value: string; onChange: (v: string) => void
}) {
  if (editing) {
    return <TextArtifact data={data} editing={true} value={value} onChange={onChange} />
  }
  const md = typeof data === 'string' ? data : String(data ?? '')
  const html = DOMPurify.sanitize(marked.parse(md) as string)
  return (
    <div
      style={{
        backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: 6,
        padding: 14, fontSize: 14, color: '#111827', maxHeight: 480, overflowY: 'auto',
      }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

function JsonArtifact({ data, editing, value, onChange, error }: {
  data: unknown; editing: boolean; value: string; onChange: (v: string) => void; error: string | null
}) {
  if (editing) {
    return (
      <div>
        <textarea
          value={value}
          onChange={e => onChange(e.target.value)}
          rows={16}
          spellCheck={false}
          style={{
            width: '100%', padding: '10px 12px', fontSize: 12, fontFamily: 'monospace',
            border: '1px solid #d1d5db', borderRadius: 6, resize: 'vertical', boxSizing: 'border-box',
          }}
        />
        {error && <div style={{ fontSize: 12, color: '#dc2626', marginTop: 6 }}>JSON error: {error}</div>}
      </div>
    )
  }
  const formatted = JSON.stringify(data ?? null, null, 2)
  return (
    <pre style={{
      backgroundColor: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 6,
      padding: 12, fontSize: 12, fontFamily: 'monospace',
      maxHeight: 480, overflowY: 'auto', color: '#111827',
    }}>
      {formatted}
    </pre>
  )
}

function ExtractionTableArtifact({ data, editing, value, onChange }: {
  data: unknown; editing: boolean; value: Record<string, string>; onChange: (v: Record<string, string>) => void
}) {
  // Single-row dict form
  if (data && typeof data === 'object' && !Array.isArray(data)) {
    const rec = data as Record<string, unknown>
    return (
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, border: '1px solid #e5e7eb', borderRadius: 6, overflow: 'hidden' }}>
        <tbody>
          {Object.entries(rec).map(([k, v]) => (
            <tr key={k} style={{ borderBottom: '1px solid #f3f4f6' }}>
              <td style={{ padding: '8px 12px', fontWeight: 600, color: '#374151', width: '32%', backgroundColor: '#f9fafb', verticalAlign: 'top' }}>
                {k}
              </td>
              <td style={{ padding: '8px 12px', color: '#111827' }}>
                {editing ? (
                  <input
                    type="text"
                    value={value[k] ?? String(v ?? '')}
                    onChange={e => onChange({ ...value, [k]: e.target.value })}
                    style={{ width: '100%', padding: '4px 8px', fontSize: 13, border: '1px solid #d1d5db', borderRadius: 4 }}
                  />
                ) : (
                  String(v ?? '')
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    )
  }
  // Multi-row list-of-dicts
  if (Array.isArray(data) && data.length > 0 && data.every(d => d && typeof d === 'object')) {
    const rows = data as Record<string, unknown>[]
    const keys = Array.from(new Set(rows.flatMap(r => Object.keys(r))))
    return (
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, border: '1px solid #e5e7eb', borderRadius: 6 }}>
          <thead>
            <tr style={{ backgroundColor: '#f9fafb' }}>
              {keys.map(k => (
                <th key={k} scope="col" style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#374151', borderBottom: '1px solid #e5e7eb' }}>
                  {k}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                {keys.map(k => (
                  <td key={k} style={{ padding: '8px 12px', color: '#111827' }}>
                    {String(r[k] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {editing && <div style={{ fontSize: 12, color: '#6b7280', marginTop: 6 }}>Multi-row tables are read-only in edit mode for now.</div>}
      </div>
    )
  }
  return <JsonArtifact data={data} editing={false} value="" onChange={() => {}} error={null} />
}

function DocumentRenderArtifact({ data }: { data: unknown }) {
  const rec = (data && typeof data === 'object') ? data as Record<string, unknown> : {}
  const filename = rec.filename as string | undefined
  const url = rec.url as string | undefined
  return (
    <div style={{
      backgroundColor: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 6, padding: 16,
      display: 'flex', alignItems: 'center', gap: 12,
    }}>
      <FileText style={{ width: 24, height: 24, color: '#6b7280' }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: '#111827' }}>
          {filename || 'Generated document'}
        </div>
        {url && (
          <a href={url} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: '#0ea5e9', textDecoration: 'none' }}>
            Open / download
          </a>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ReviewDetailPage() {
  const params = useParams({ strict: false }) as { uuid: string }
  const navigate = useNavigate()
  const [review, setReview] = useState<ReviewDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState('')
  const [editJson, setEditJson] = useState('')
  const [editTable, setEditTable] = useState<Record<string, string>>({})
  const [jsonError, setJsonError] = useState<string | null>(null)

  const [comments, setComments] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getReview(params.uuid)
      .then(r => {
        if (cancelled) return
        setReview(r)
        const inner = unwrapArtifact(r.data_for_review)
        if (typeof inner === 'string') setEditText(inner)
        else setEditText(typeof inner === 'object' ? '' : String(inner ?? ''))
        if (inner && typeof inner === 'object' && !Array.isArray(inner)) {
          const rec = inner as Record<string, unknown>
          const seed: Record<string, string> = {}
          for (const k of Object.keys(rec)) seed[k] = String(rec[k] ?? '')
          setEditTable(seed)
        }
        try { setEditJson(JSON.stringify(inner ?? null, null, 2)) } catch { setEditJson('') }
      })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load review') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [params.uuid])

  const computeEditedArtifact = (): { ok: true; value: Record<string, unknown> | null } | { ok: false; reason: string } => {
    if (!review) return { ok: true, value: null }
    if (!editing) return { ok: true, value: null }
    const k: ArtifactKind = review.artifact_kind
    if (k === 'text' || k === 'markdown') {
      const inner = unwrapArtifact(review.data_for_review)
      if (typeof inner === 'string' && editText === inner) return { ok: true, value: null }
      // Wrap so the engine receives a value of the same shape it had
      return { ok: true, value: { value: editText } }
    }
    if (k === 'json') {
      try {
        const parsed = JSON.parse(editJson)
        const wrapped = (parsed && typeof parsed === 'object' && !Array.isArray(parsed))
          ? parsed as Record<string, unknown>
          : { value: parsed }
        return { ok: true, value: wrapped }
      } catch (e) {
        return { ok: false, reason: e instanceof Error ? e.message : 'Invalid JSON' }
      }
    }
    if (k === 'extraction_table') {
      const inner = unwrapArtifact(review.data_for_review)
      if (Array.isArray(inner)) return { ok: true, value: null }  // multi-row read-only for v1
      return { ok: true, value: editTable }
    }
    return { ok: true, value: null }
  }

  const handleApprove = async () => {
    if (!review) return
    const edited = computeEditedArtifact()
    if (!edited.ok) {
      setSubmitError(edited.reason)
      return
    }
    setSubmitting(true)
    setSubmitError(null)
    try {
      await approveReview(review.uuid, { comments, edited_artifact: edited.value })
      navigate({ to: '/reviews' as never })
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : 'Failed to approve')
      setSubmitting(false)
    }
  }

  const handleReject = async () => {
    if (!review) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      await rejectReview(review.uuid, comments)
      navigate({ to: '/reviews' as never })
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : 'Failed to reject')
      setSubmitting(false)
    }
  }

  if (loading) return <div style={{ padding: 24, fontSize: 13, color: '#6b7280' }}>Loading...</div>
  if (error) return <div style={{ padding: 24, fontSize: 13, color: '#dc2626' }}>{error}</div>
  if (!review) return null

  const inner = unwrapArtifact(review.data_for_review)
  const isPending = review.status === 'pending'

  // Validate JSON live so the user sees errors before submit
  if (editing && review.artifact_kind === 'json') {
    try { JSON.parse(editJson); if (jsonError) setJsonError(null) }
    catch (e) { const msg = e instanceof Error ? e.message : 'Invalid JSON'; if (msg !== jsonError) setJsonError(msg) }
  }

  const renderArtifact = () => {
    switch (review.artifact_kind) {
      case 'text':
        return <TextArtifact data={inner} editing={editing} value={editText} onChange={setEditText} />
      case 'markdown':
        return <MarkdownArtifact data={inner} editing={editing} value={editText} onChange={setEditText} />
      case 'extraction_table':
        return <ExtractionTableArtifact data={inner} editing={editing} value={editTable} onChange={setEditTable} />
      case 'document_render':
        return <DocumentRenderArtifact data={inner} />
      case 'json':
      case 'unknown':
      default:
        return <JsonArtifact data={inner} editing={editing} value={editJson} onChange={setEditJson} error={jsonError} />
    }
  }

  const editable = ['text', 'markdown', 'json', 'extraction_table'].includes(review.artifact_kind) && isPending
  const isMultiRowTable = review.artifact_kind === 'extraction_table' && Array.isArray(inner)

  return (
    <>
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-[1000] focus:rounded-md focus:bg-white focus:px-4 focus:py-2 focus:shadow-lg focus:ring-2 focus:ring-highlight">Skip to main content</a>
    <main id="main-content" style={{ maxWidth: 920, margin: '0 auto', padding: '24px 24px 80px' }}>
      <Link
        to="/reviews"
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#6b7280', textDecoration: 'none', marginBottom: 16 }}
      >
        <ArrowLeft style={{ width: 14, height: 14 }} />
        Back to reviews
      </Link>

      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8, gap: 12 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: '#111827', margin: 0 }}>
          {review.workflow_name || 'Workflow'}
        </h1>
        <span style={{
          padding: '3px 10px', borderRadius: 999, fontSize: 11, fontWeight: 600,
          backgroundColor: review.status === 'pending' ? '#fef3c7'
            : review.status === 'approved' ? '#dcfce7'
            : review.status === 'rejected' ? '#fee2e2' : '#e5e7eb',
          color: review.status === 'pending' ? '#92400e'
            : review.status === 'approved' ? '#166534'
            : review.status === 'rejected' ? '#991b1b' : '#374151',
        }}>
          {review.status}
        </span>
      </div>

      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 24 }}>
        Step "{review.step_name}"
        {review.requester ? ` · launched by ${review.requester.name || review.requester.user_id}` : ''}
        {review.created_at ? ` · ${relativeTime(review.created_at)}` : ''}
        {review.expires_at ? ` · due ${new Date(review.expires_at).toLocaleString()}` : ''}
      </div>

      {review.review_instructions && (
        <div style={{
          marginBottom: 20, padding: '12px 14px', borderRadius: 8,
          backgroundColor: '#fefce8', border: '1px solid #fde68a', color: '#713f12', fontSize: 13,
        }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Review instructions</div>
          {review.review_instructions}
        </div>
      )}

      {review.source_docs.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', marginBottom: 6 }}>Source documents</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {review.source_docs.map(d => (
              <span key={d.uuid} style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '3px 10px', borderRadius: 6, fontSize: 12,
                backgroundColor: '#f3f4f6', color: '#374151',
              }}>
                <FileText style={{ width: 12, height: 12 }} />
                {d.title}
              </span>
            ))}
          </div>
        </div>
      )}

      <div style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>
            Output to review
          </div>
          {editable && !isMultiRowTable && (
            editing ? (
              <button
                onClick={() => { setEditing(false); setSubmitError(null) }}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#6b7280', background: 'none', border: 'none', cursor: 'pointer' }}
              >
                <RotateCcw style={{ width: 12, height: 12 }} />
                Discard edits
              </button>
            ) : (
              <button
                onClick={() => setEditing(true)}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#0ea5e9', background: 'none', border: 'none', cursor: 'pointer' }}
              >
                <Pencil style={{ width: 12, height: 12 }} />
                Edit before approving
              </button>
            )
          )}
        </div>
        {renderArtifact()}
      </div>

      {isPending && (
        <>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
              Comments (optional)
            </label>
            <textarea
              value={comments}
              onChange={e => setComments(e.target.value)}
              rows={3}
              placeholder="Notes for the workflow owner..."
              style={{
                width: '100%', padding: '8px 12px', fontSize: 13, fontFamily: 'inherit',
                border: '1px solid #d1d5db', borderRadius: 6, resize: 'vertical', boxSizing: 'border-box',
              }}
            />
          </div>

          {submitError && (
            <div style={{ fontSize: 13, color: '#dc2626', marginBottom: 12 }}>{submitError}</div>
          )}

          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={handleApprove}
              disabled={submitting}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '8px 18px', fontSize: 13, fontWeight: 600,
                backgroundColor: submitting ? '#86efac' : '#16a34a', color: '#fff',
                border: 'none', borderRadius: 6, cursor: submitting ? 'default' : 'pointer',
              }}
            >
              <CheckCircle style={{ width: 14, height: 14 }} />
              {editing ? 'Approve with edits' : 'Approve'}
            </button>
            <button
              onClick={handleReject}
              disabled={submitting}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '8px 18px', fontSize: 13, fontWeight: 600,
                backgroundColor: '#fff', color: '#dc2626',
                border: '1px solid #fca5a5', borderRadius: 6, cursor: submitting ? 'default' : 'pointer',
              }}
            >
              <XCircle style={{ width: 14, height: 14 }} />
              Reject
            </button>
          </div>
        </>
      )}

      {!isPending && (
        <div style={{ padding: 14, borderRadius: 8, backgroundColor: '#f9fafb', border: '1px solid #e5e7eb', fontSize: 13, color: '#374151' }}>
          {review.status === 'approved' ? 'Approved' : review.status === 'rejected' ? 'Rejected' : `Status: ${review.status}`}
          {review.reviewer_user_id ? ` by ${review.reviewer_user_id}` : ''}
          {review.decision_at ? ` · ${new Date(review.decision_at).toLocaleString()}` : ''}
          {review.reviewer_comments && (
            <div style={{ marginTop: 6, color: '#4b5563' }}>"{review.reviewer_comments}"</div>
          )}
        </div>
      )}
    </main>
    </>
  )
}
