import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from '@tanstack/react-router'
import { ArrowLeft, CheckCircle, XCircle, FileText, Pencil, RotateCcw } from 'lucide-react'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { getReview, approveReview, rejectReview } from '../api/reviews'
import type { ReviewDetail, ArtifactKind } from '../api/reviews'
import { relativeTime } from '../utils/time'
import { PageLayout } from '../components/layout/PageLayout'
import { useMyReviewCount } from '../hooks/useMyReviewCount'

const DocumentViewer = lazy(() => import('../components/files/DocumentViewer').then(module => ({ default: module.DocumentViewer })))

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
        aria-label="Edit review output"
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
    <pre tabIndex={0} role="region" aria-label="Review output" style={{
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
    <div tabIndex={0} role="region" aria-label="Review output"
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
          aria-label="Edit review output as JSON"
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
    <pre tabIndex={0} role="region" aria-label="Review output" style={{
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
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, border: '1px solid #e5e7eb', borderRadius: 6, overflow: 'hidden', tableLayout: 'fixed', overflowWrap: 'anywhere' }}>
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
                    aria-label={`Edit ${k}`}
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
      <div tabIndex={0} role="region" aria-label="Review extraction results — scroll to see all columns" style={{ overflowX: 'auto' }}>
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
          <a href={url} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: '#0369a1', textDecoration: 'none' }}>
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
  const { refresh: refreshReviewCount } = useMyReviewCount()
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
  const [source, setSource] = useState<{ uuid: string; title: string } | null>(null)
  const sourceRegion = useRef<HTMLDivElement>(null)
  const sourceTrigger = useRef<HTMLButtonElement | null>(null)
  const decisionPending = useRef(false)
  useEffect(() => { if (source) sourceRegion.current?.focus() }, [source])
  const closeSource = () => {
    setSource(null)
    requestAnimationFrame(() => sourceTrigger.current?.focus({ preventScroll: true }))
  }


  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setSource(null)
    setEditing(false)
    setComments('')
    setSubmitError(null)
    setSubmitting(false)
    decisionPending.current = false
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
    if (!review || decisionPending.current) return
    const edited = computeEditedArtifact()
    if (!edited.ok) {
      setSubmitError(edited.reason)
      return
    }
    decisionPending.current = true
    setSubmitting(true)
    setSubmitError(null)
    try {
      await approveReview(review.uuid, { comments, edited_artifact: edited.value })
      // Re-poll now rather than waiting out the badge's 30s tick — a reviewer
      // who just cleared their last approval should not still see a "1".
      void refreshReviewCount()
      navigate({ to: '/reviews' as never })
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : 'Failed to approve')
      decisionPending.current = false
      setSubmitting(false)
    }
  }

  const handleReject = async () => {
    if (!review || decisionPending.current) return
    decisionPending.current = true
    setSubmitting(true)
    setSubmitError(null)
    try {
      await rejectReview(review.uuid, comments)
      void refreshReviewCount()
      navigate({ to: '/reviews' as never })
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : 'Failed to reject')
      decisionPending.current = false
      setSubmitting(false)
    }
  }

  // Wrapped too: a review that 404s (wrong link, already deleted) otherwise
  // dropped the user on a bare error string with no way back into the app.
  if (loading) {
    return <PageLayout><div role="status" aria-live="polite" style={{ fontSize: 13, color: '#6b7280' }}>Loading...</div></PageLayout>
  }
  if (error) {
    return <PageLayout><div role="status" aria-live="polite" style={{ fontSize: 13, color: '#dc2626' }}>{error}</div></PageLayout>
  }
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
    <PageLayout>
      <div style={{ maxWidth: 920, margin: '0 auto', paddingBottom: 80 }}>
        <Link
          to="/reviews"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#6b7280', textDecoration: 'none', marginBottom: 16 }}
        >
          <ArrowLeft style={{ width: 14, height: 14 }} />
          Back to reviews
        </Link>

        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8, gap: 12 }}>
          <h1 style={{ flex: '1 1 180px', minWidth: 0, fontSize: 22, fontWeight: 700, color: '#111827', margin: 0 }}>
            {review.workflow_name || 'Workflow'}
          </h1>
          <span style={{
            flexShrink: 0, whiteSpace: 'nowrap', padding: '3px 10px', borderRadius: 999, fontSize: 11, fontWeight: 600,
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
                <button type="button" key={d.uuid} aria-expanded={source?.uuid === d.uuid} aria-controls="review-source-viewer" onClick={event => { sourceTrigger.current = event.currentTarget; setSource(d) }} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  padding: '3px 10px', borderRadius: 6, fontSize: 12,
                  backgroundColor: '#f3f4f6', color: '#374151', border: '1px solid #d1d5db', cursor: 'pointer', overflowWrap: 'anywhere', textAlign: 'left',
                }}>
                  <FileText style={{ width: 12, height: 12 }} />
                  Inspect {d.title}
                </button>
              ))}
            </div>
          </div>
        )}

        {source && <div id="review-source-viewer" ref={sourceRegion} tabIndex={-1} role="region" aria-label={`Source document: ${source.title}`} style={{ marginBottom: 20, border: '1px solid #d1d5db', borderRadius: 8, overflow: 'hidden' }} onKeyDown={event => { if (event.key === 'Escape' && !event.defaultPrevented) { event.preventDefault(); closeSource() } }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: 8, padding: 12, fontSize: 13 }}><strong style={{ overflowWrap: 'anywhere' }}>{source.title}</strong><button type="button" onClick={closeSource}>Close source</button></div>
          <div style={{ height: 'min(55vh, 550px)', minHeight: 220 }}><Suspense fallback={<p role="status">Loading source…</p>}><DocumentViewer docUuid={source.uuid} /></Suspense></div>
        </div>}
        <div style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>
              Output to review
            </div>
            {editable && !isMultiRowTable && (
              editing ? (
                <button
                  onClick={() => { setEditing(false); setSubmitError(null); setEditText(typeof inner === 'string' ? inner : ''); setEditJson(JSON.stringify(inner ?? null, null, 2)); setEditTable(inner && typeof inner === 'object' && !Array.isArray(inner) ? Object.fromEntries(Object.entries(inner).map(([key, value]) => [key, String(value ?? '')])) : {}) }}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#6b7280', background: 'none', border: 'none', cursor: 'pointer' }}
                >
                  <RotateCcw style={{ width: 12, height: 12 }} />
                  Discard edits
                </button>
              ) : (
                <button
                  onClick={() => setEditing(true)}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#0369a1', background: 'none', border: 'none', cursor: 'pointer' }}
                >
                  <Pencil style={{ width: 12, height: 12 }} />
                  Edit before approving
                </button>
              )
            )}
          </div>
          {renderArtifact()}
          {editing && <details style={{ marginTop: 12, fontSize: 13 }}><summary>Compare with original output</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', padding: 12, border: '1px solid #e5e7eb' }}>{typeof unwrapArtifact(review.data_for_review) === 'string' ? String(unwrapArtifact(review.data_for_review)) : JSON.stringify(unwrapArtifact(review.data_for_review), null, 2)}</pre></details>}
        </div>

        {isPending && (
          <>
            <p style={{ fontSize: 13, color: '#59616b', lineHeight: 1.6 }}>Approval accepts this output for the workflow’s next step. It does not publish the item or certify institutional compliance.{editing && ' Your edited output will replace the proposed output when you approve; compare it with the original above.'}</p>
            <div style={{ marginBottom: 16 }}>
              <label htmlFor="review-comments" style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
                Comments (optional)
              </label>
              <textarea
                id="review-comments"
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
              <div role="alert" style={{ fontSize: 13, color: '#b91c1c', marginBottom: 12 }}>{submitError}</div>
            )}

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              <button
                onClick={handleApprove}
                disabled={submitting}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '8px 18px', fontSize: 13, fontWeight: 600,
                  backgroundColor: '#15803d', color: '#fff',
                  border: 'none', borderRadius: 6, cursor: submitting ? 'default' : 'pointer',
                }}
              >
                <CheckCircle style={{ width: 14, height: 14 }} />
                {submitting ? 'Submitting decision…' : editing ? 'Approve with edits' : 'Approve'}
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
            {review.status === 'approved' && <p style={{ marginTop: 6, color: '#4b5563' }}>Your approval is recorded. Open the workflow to check whether subsequent steps completed.</p>}
            {review.reviewer_comments && (
              <div style={{ marginTop: 6, color: '#4b5563' }}>"{review.reviewer_comments}"</div>
            )}
          </div>
        )}
      </div>
    </PageLayout>
  )
}
