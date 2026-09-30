import { usePanelEffect } from '../shared/usePanelEffect'
import { useEffect, useState } from 'react'
import { createPortal } from '../shared/panelPortal'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { X, Plus, Trash2, Save, ExternalLink, AlertTriangle } from 'lucide-react'
import { claimVerificationRequest, releaseVerificationRequest, setExaminerAdditions } from '../../api/library'
import type { VerificationRequest, ExaminerBaselineAdditions } from '../../types/library'

interface Props {
  request: VerificationRequest
  currentUserId: string
  onClose: () => void
  onSaved: () => void
}

interface ExtractionRow { document_uuid: string; expected_json: string; note: string }
interface KBRow { query: string; expected_answer: string; note: string }
interface WorkflowRow { input: string; expected_output: string; note: string }
interface CheckRow { description: string; target_step: string }

const inputStyle: React.CSSProperties = {
  width: '100%', padding: "var(--workspace-space-6) var(--workspace-space-12)",
  border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)',
  fontSize: 'var(--workspace-font-meta)', fontFamily: 'inherit', boxSizing: 'border-box',
}
const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: 'var(--workspace-font-meta)', fontWeight: 600, color: '#374151', marginBottom: 'var(--workspace-space-4)',
}
const sectionTitle: React.CSSProperties = {
  fontSize: 'var(--workspace-font-meta)', fontWeight: 700, color: '#111827', marginBottom: 'var(--workspace-space-8)',
  textTransform: 'uppercase', letterSpacing: '0.04em',
}

function readAdditions(req: VerificationRequest): {
  extraction: ExtractionRow[]
  kb: KBRow[]
  workflow: WorkflowRow[]
  checks: CheckRow[]
} {
  const a = req.examiner_baseline_additions || {}
  return {
    extraction: (a.test_cases || []).map(tc => ({
      document_uuid: typeof tc.document_uuid === 'string' ? tc.document_uuid : '',
      expected_json: tc.expected ? JSON.stringify(tc.expected, null, 2) : '',
      note: typeof tc.note === 'string' ? tc.note : '',
    })),
    kb: (a.queries || []).map(q => ({
      query: q.query || '',
      expected_answer: q.expected_answer || '',
      note: q.note || '',
    })),
    workflow: (a.regression_inputs || []).map(r => ({
      input: r.input || '',
      expected_output: r.expected_output || '',
      note: r.note || '',
    })),
    checks: (a.checks || []).map(c => ({
      description: c.description || '',
      target_step: c.target_step || '',
    })),
  }
}

export function ExaminerValidationDrawer({ request, currentUserId, onClose, onSaved }: Props) {
  const initial = readAdditions(request)
  const [extractionRows, setExtractionRows] = useState<ExtractionRow[]>(initial.extraction)
  const [kbRows, setKbRows] = useState<KBRow[]>(initial.kb)
  const [workflowRows, setWorkflowRows] = useState<WorkflowRow[]>(initial.workflow)
  const [checkRows, setCheckRows] = useState<CheckRow[]>(initial.checks)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [claimError, setClaimError] = useState<string | null>(null)
  const [claimed, setClaimed] = useState(request.claimed_by_user_id === currentUserId)

  const otherHolder = request.claimed_by_user_id && request.claimed_by_user_id !== currentUserId

  useEffect(() => {
    // Try to claim on open if not already held
    if (!request.claimed_by_user_id || request.claimed_by_user_id === currentUserId) {
      claimVerificationRequest(request.uuid)
        .then(() => setClaimed(true))
        .catch(err => setClaimError(err instanceof Error ? err.message : 'Could not claim request'))
    }
    return () => {
      // Best-effort release on unmount
      if (request.claimed_by_user_id === currentUserId || !request.claimed_by_user_id) {
        releaseVerificationRequest(request.uuid).catch(() => {})
      }
    }
  }, [request.uuid, request.claimed_by_user_id, currentUserId])

  usePanelEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const additions: ExaminerBaselineAdditions = {}
      if (request.item_kind === 'search_set') {
        const tcs = extractionRows
          .filter(r => r.document_uuid || r.expected_json || r.note)
          .map(r => {
            let expected: Record<string, unknown> | undefined
            if (r.expected_json.trim()) {
              try {
                expected = JSON.parse(r.expected_json)
              } catch {
                throw new Error(`Invalid JSON in expected values for "${r.document_uuid || 'row'}"`)
              }
            }
            return {
              document_uuid: r.document_uuid || undefined,
              expected,
              note: r.note || undefined,
            }
          })
        if (tcs.length) additions.test_cases = tcs
      } else if (request.item_kind === 'knowledge_base') {
        const qs = kbRows
          .filter(r => r.query.trim())
          .map(r => ({
            query: r.query.trim(),
            expected_answer: r.expected_answer.trim() || undefined,
            note: r.note.trim() || undefined,
          }))
        if (qs.length) additions.queries = qs
      } else {
        const inputs = workflowRows
          .filter(r => r.input.trim())
          .map(r => ({
            input: r.input.trim(),
            expected_output: r.expected_output.trim() || undefined,
            note: r.note.trim() || undefined,
          }))
        if (inputs.length) additions.regression_inputs = inputs
        const checks = checkRows
          .filter(r => r.description.trim())
          .map(r => ({
            description: r.description.trim(),
            target_step: r.target_step.trim() || undefined,
          }))
        if (checks.length) additions.checks = checks
      }
      await setExaminerAdditions(request.uuid, additions)
      onSaved()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const submitterSnapshot = request.validation_snapshot as Record<string, unknown> | null
  const submitterScore = request.validation_score

  const itemKindLabel =
    request.item_kind === 'workflow' ? 'workflow'
    : request.item_kind === 'knowledge_base' ? 'knowledge base'
    : 'extraction'

  const content = (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9998, display: 'flex', justifyContent: 'flex-end',
      backgroundColor: 'rgba(0,0,0,0.35)',
    }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Validation workshop"
        style={{
        background: '#fff', width: '100%', maxWidth: 720, height: '100vh',
        display: 'flex', flexDirection: 'column', boxShadow: '-10px 0 30px rgba(0,0,0,0.2)',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: "var(--workspace-space-16) var(--workspace-space-20)", borderBottom: "1px solid var(--workspace-border)",
        }}>
          <div>
            <div style={{ fontSize: 'var(--workspace-font-body)', fontWeight: 700, color: '#111' }}>Validation workshop</div>
            <div style={{ fontSize: 'var(--workspace-font-meta)', color: '#6b7280', marginTop: 'var(--workspace-space-2)' }}>
              Curate examiner-side validation baseline for this {itemKindLabel}. Additions are merged into the official baseline at approval.
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', padding: 'var(--workspace-space-4)',
          }}>
            <X size={18} />
          </button>
        </div>

        {/* Claim banner */}
        {otherHolder && (
          <div style={{
            margin: "var(--workspace-space-12) var(--workspace-space-20) 0", padding: "var(--workspace-space-8) var(--workspace-space-12)",
            background: '#fef3c7', border: '1px solid #fcd34d', borderRadius: 'var(--workspace-radius-small)',
            fontSize: 'var(--workspace-font-meta)', color: '#78350f', display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-6)',
          }}>
            <AlertTriangle size={14} />
            Currently held by another reviewer. Your edits may collide.
          </div>
        )}
        {claimError && !otherHolder && (
          <div
            role="status"
            aria-live="polite"
            style={{
            margin: "var(--workspace-space-12) var(--workspace-space-20) 0", padding: "var(--workspace-space-8) var(--workspace-space-12)",
            background: '#fee2e2', border: '1px solid #fca5a5', borderRadius: 'var(--workspace-radius-small)',
            fontSize: 'var(--workspace-font-meta)', color: '#991b1b',
          }}>
            {claimError}
          </div>
        )}
        {claimed && !otherHolder && (
          <div
            role="status"
            aria-live="polite"
            style={{
            margin: "var(--workspace-space-12) var(--workspace-space-20) 0", padding: "var(--workspace-space-6) var(--workspace-space-12)",
            background: '#ecfdf5', border: '1px solid #a7f3d0', borderRadius: 'var(--workspace-radius-small)',
            fontSize: 'var(--workspace-font-meta)', color: '#065f46',
          }}>
            Claimed by you. Other reviewers will see this as in-progress.
          </div>
        )}

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: "var(--workspace-space-16) var(--workspace-space-20)", display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-20)' }}>
          {/* Submitter snapshot context */}
          <section>
            <div style={sectionTitle}>Submitter validation</div>
            {request.validation_origin === 'pending_admin_validation' ? (
              <div style={{ fontSize: 'var(--workspace-font-meta)', color: '#92400e', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-8) var(--workspace-space-12)" }}>
                Submitter requested admin validation. No baseline data was provided.
              </div>
            ) : submitterSnapshot ? (
              <div style={{ fontSize: 'var(--workspace-font-meta)', color: '#374151', background: '#f9fafb', border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-12) var(--workspace-space-12)", display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-4)' }}>
                {submitterScore != null && (
                  <div>Submitter score: <strong>{Math.round(submitterScore)}%</strong></div>
                )}
                {request.item_kind === 'search_set' && (
                  <div>Submitter test cases: <strong>{Array.isArray((submitterSnapshot as Record<string, unknown>).test_cases) ? ((submitterSnapshot as Record<string, unknown>).test_cases as unknown[]).length : 0}</strong></div>
                )}
                {request.item_kind === 'knowledge_base' && (
                  <div>Submitter judged queries: <strong>{Array.isArray((submitterSnapshot as Record<string, unknown>).queries) ? ((submitterSnapshot as Record<string, unknown>).queries as unknown[]).length : Array.isArray((submitterSnapshot as Record<string, unknown>).sources) ? ((submitterSnapshot as Record<string, unknown>).sources as unknown[]).length : 0}</strong></div>
                )}
                {request.item_kind === 'workflow' && (
                  <div>Submitter checks: <strong>{Array.isArray((submitterSnapshot as Record<string, unknown>).checks) ? ((submitterSnapshot as Record<string, unknown>).checks as unknown[]).length : 0}</strong></div>
                )}
                <div style={{ color: '#6b7280', fontSize: 'var(--workspace-font-meta)', marginTop: 'var(--workspace-space-4)' }}>
                  Your additions extend this set, they don't replace it. Edits to submitter cases require a return-for-rework instead.
                </div>
              </div>
            ) : (
              <div style={{ fontSize: 'var(--workspace-font-meta)', color: '#6b7280' }}>No submitter validation attached.</div>
            )}
          </section>

          {/* Examiner additions — kind-aware editor */}
          {request.item_kind === 'search_set' && (
            <section>
              <div style={sectionTitle}>Examiner test cases</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-8)' }}>
                {extractionRows.map((row, i) => (
                  <div key={i} style={{ border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: 'var(--workspace-space-12)', display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-6)' }}>
                    <div>
                      <label style={labelStyle}>Document UUID</label>
                      <input value={row.document_uuid} onChange={e => {
                        const copy = [...extractionRows]; copy[i] = { ...row, document_uuid: e.target.value }; setExtractionRows(copy)
                      }} placeholder="(optional) document UUID" style={inputStyle} />
                    </div>
                    <div>
                      <label style={labelStyle}>Expected values (JSON)</label>
                      <textarea value={row.expected_json} onChange={e => {
                        const copy = [...extractionRows]; copy[i] = { ...row, expected_json: e.target.value }; setExtractionRows(copy)
                      }} placeholder='{"field_name": "expected value"}' rows={3} style={{ ...inputStyle, resize: 'vertical', fontFamily: 'ui-monospace, monospace' }} />
                    </div>
                    <div>
                      <label style={labelStyle}>Note</label>
                      <input value={row.note} onChange={e => {
                        const copy = [...extractionRows]; copy[i] = { ...row, note: e.target.value }; setExtractionRows(copy)
                      }} placeholder="Why this case is important" style={inputStyle} />
                    </div>
                    <button onClick={() => setExtractionRows(extractionRows.filter((_, j) => j !== i))}
                      style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)', fontSize: 'var(--workspace-font-meta)', color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer' }}>
                      <Trash2 size={12} /> Remove
                    </button>
                  </div>
                ))}
                <button onClick={() => setExtractionRows([...extractionRows, { document_uuid: '', expected_json: '', note: '' }])}
                  style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)', fontSize: 'var(--workspace-font-meta)', color: '#374151', background: '#f3f4f6', border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-6) var(--workspace-space-12)", cursor: 'pointer' }}>
                  <Plus size={12} /> Add test case
                </button>
              </div>
            </section>
          )}

          {request.item_kind === 'knowledge_base' && (
            <section>
              <div style={sectionTitle}>Examiner queries</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-8)' }}>
                {kbRows.map((row, i) => (
                  <div key={i} style={{ border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: 'var(--workspace-space-12)', display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-6)' }}>
                    <div>
                      <label style={labelStyle}>Query</label>
                      <input value={row.query} onChange={e => {
                        const copy = [...kbRows]; copy[i] = { ...row, query: e.target.value }; setKbRows(copy)
                      }} placeholder="What question should the KB be able to answer?" style={inputStyle} />
                    </div>
                    <div>
                      <label style={labelStyle}>Expected answer (optional)</label>
                      <textarea value={row.expected_answer} onChange={e => {
                        const copy = [...kbRows]; copy[i] = { ...row, expected_answer: e.target.value }; setKbRows(copy)
                      }} rows={2} placeholder="Used by the judge to score the retrieved answer" style={{ ...inputStyle, resize: 'vertical' }} />
                    </div>
                    <div>
                      <label style={labelStyle}>Note</label>
                      <input value={row.note} onChange={e => {
                        const copy = [...kbRows]; copy[i] = { ...row, note: e.target.value }; setKbRows(copy)
                      }} placeholder="Why this query is institutionally important" style={inputStyle} />
                    </div>
                    <button onClick={() => setKbRows(kbRows.filter((_, j) => j !== i))}
                      style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)', fontSize: 'var(--workspace-font-meta)', color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer' }}>
                      <Trash2 size={12} /> Remove
                    </button>
                  </div>
                ))}
                <button onClick={() => setKbRows([...kbRows, { query: '', expected_answer: '', note: '' }])}
                  style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)', fontSize: 'var(--workspace-font-meta)', color: '#374151', background: '#f3f4f6', border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-6) var(--workspace-space-12)", cursor: 'pointer' }}>
                  <Plus size={12} /> Add query
                </button>
              </div>
            </section>
          )}

          {request.item_kind === 'workflow' && (
            <>
              <section>
                <div style={sectionTitle}>Examiner regression inputs</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-8)' }}>
                  {workflowRows.map((row, i) => (
                    <div key={i} style={{ border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: 'var(--workspace-space-12)', display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-6)' }}>
                      <div>
                        <label style={labelStyle}>Input</label>
                        <textarea value={row.input} onChange={e => {
                          const copy = [...workflowRows]; copy[i] = { ...row, input: e.target.value }; setWorkflowRows(copy)
                        }} rows={2} placeholder="A representative input the workflow should handle" style={{ ...inputStyle, resize: 'vertical' }} />
                      </div>
                      <div>
                        <label style={labelStyle}>Expected output (optional)</label>
                        <textarea value={row.expected_output} onChange={e => {
                          const copy = [...workflowRows]; copy[i] = { ...row, expected_output: e.target.value }; setWorkflowRows(copy)
                        }} rows={2} placeholder="What the workflow should produce" style={{ ...inputStyle, resize: 'vertical' }} />
                      </div>
                      <div>
                        <label style={labelStyle}>Note</label>
                        <input value={row.note} onChange={e => {
                          const copy = [...workflowRows]; copy[i] = { ...row, note: e.target.value }; setWorkflowRows(copy)
                        }} placeholder="Why this regression input matters" style={inputStyle} />
                      </div>
                      <button onClick={() => setWorkflowRows(workflowRows.filter((_, j) => j !== i))}
                        style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)', fontSize: 'var(--workspace-font-meta)', color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer' }}>
                        <Trash2 size={12} /> Remove
                      </button>
                    </div>
                  ))}
                  <button onClick={() => setWorkflowRows([...workflowRows, { input: '', expected_output: '', note: '' }])}
                    style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)', fontSize: 'var(--workspace-font-meta)', color: '#374151', background: '#f3f4f6', border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-6) var(--workspace-space-12)", cursor: 'pointer' }}>
                    <Plus size={12} /> Add regression input
                  </button>
                </div>
              </section>

              <section>
                <div style={sectionTitle}>Examiner checks</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-8)' }}>
                  {checkRows.map((row, i) => (
                    <div key={i} style={{ border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: 'var(--workspace-space-12)', display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-6)' }}>
                      <div>
                        <label style={labelStyle}>Check description</label>
                        <input value={row.description} onChange={e => {
                          const copy = [...checkRows]; copy[i] = { ...row, description: e.target.value }; setCheckRows(copy)
                        }} placeholder="What must the output satisfy?" style={inputStyle} />
                      </div>
                      <div>
                        <label style={labelStyle}>Target step (optional)</label>
                        <input value={row.target_step} onChange={e => {
                          const copy = [...checkRows]; copy[i] = { ...row, target_step: e.target.value }; setCheckRows(copy)
                        }} placeholder="Step ID or name" style={inputStyle} />
                      </div>
                      <button onClick={() => setCheckRows(checkRows.filter((_, j) => j !== i))}
                        style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)', fontSize: 'var(--workspace-font-meta)', color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer' }}>
                        <Trash2 size={12} /> Remove
                      </button>
                    </div>
                  ))}
                  <button onClick={() => setCheckRows([...checkRows, { description: '', target_step: '' }])}
                    style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)', fontSize: 'var(--workspace-font-meta)', color: '#374151', background: '#f3f4f6', border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-6) var(--workspace-space-12)", cursor: 'pointer' }}>
                    <Plus size={12} /> Add check
                  </button>
                </div>
              </section>
            </>
          )}

          <div style={{ fontSize: 'var(--workspace-font-meta)', color: '#6b7280', background: '#f9fafb', border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-8) var(--workspace-space-12)", display: 'flex', alignItems: 'flex-start', gap: 'var(--workspace-space-6)' }}>
            <ExternalLink size={12} style={{ marginTop: 'var(--workspace-space-2)', flexShrink: 0 }} />
            <span>
              To run validation against your additions before approving, open the item directly (external-link icon on the queue row) and use its Validate tab. Saved additions will be merged into the pinned baseline at approval time.
            </span>
          </div>

          {error && (
            <div role="status" aria-live="polite" style={{ padding: "var(--workspace-space-8) var(--workspace-space-12)", borderRadius: 'var(--workspace-radius-small)', background: '#fee2e2', border: '1px solid #fca5a5', fontSize: 'var(--workspace-font-meta)', color: '#991b1b' }}>
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: "var(--workspace-space-12) var(--workspace-space-20)", borderTop: "1px solid var(--workspace-border)",
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 'var(--workspace-space-12)',
        }}>
          <button onClick={onClose} style={{
            padding: "7px var(--workspace-space-16)", borderRadius: 'var(--workspace-radius-small)', border: "1px solid var(--workspace-border)",
            background: '#fff', fontSize: 'var(--workspace-font-control)', fontWeight: 600, cursor: 'pointer', color: '#374151',
          }}>
            Close
          </button>
          <button onClick={handleSave} disabled={saving} style={{
            display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-6)',
            padding: "7px var(--workspace-space-20)", borderRadius: 'var(--workspace-radius-small)', border: 'none',
            background: '#111827', color: '#fff', fontSize: 'var(--workspace-font-control)', fontWeight: 600,
            cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.6 : 1,
          }}>
            <Save size={14} />
            {saving ? 'Saving…' : 'Save additions'}
          </button>
        </div>
      </div>
      </FocusTrap>
    </div>
  )

  return createPortal(content, document.body)
}
