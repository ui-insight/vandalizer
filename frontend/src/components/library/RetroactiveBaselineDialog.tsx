import { usePanelEffect } from '../shared/usePanelEffect'
import { useState } from 'react'
import { createPortal } from '../shared/panelPortal'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { X, Save, AlertTriangle, Plus, Trash2 } from 'lucide-react'
import { pinRetroactiveBaseline } from '../../api/library'
import type { CatalogCoverageItem } from '../../types/library'

interface Props {
  item: CatalogCoverageItem
  onClose: () => void
  onSaved: () => void
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: "var(--workspace-space-6) var(--workspace-space-12)",
  border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)',
  fontSize: 'var(--workspace-font-meta)', fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box',
}
const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: 'var(--workspace-font-meta)', fontWeight: 600, color: '#374151', marginBottom: 'var(--workspace-space-4)',
}

function kindLabel(k: string) {
  if (k === 'workflow') return 'workflow'
  if (k === 'search_set') return 'extraction'
  if (k === 'knowledge_base') return 'knowledge base'
  return k
}

interface ExtractionTC { document_uuid: string; expected_json: string }
interface KBQuery { query: string; expected_answer: string }
interface WorkflowInput { input: string; expected_output: string }

export function RetroactiveBaselineDialog({ item, onClose, onSaved }: Props) {
  const [extractionRows, setExtractionRows] = useState<ExtractionTC[]>([])
  const [kbRows, setKbRows] = useState<KBQuery[]>([])
  const [workflowRows, setWorkflowRows] = useState<WorkflowInput[]>([])
  const [score, setScore] = useState<string>('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)

  usePanelEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    setWarning(null)
    try {
      const baseline: Record<string, unknown> = {}
      if (item.item_kind === 'search_set') {
        const tcs = extractionRows
          .filter(r => r.document_uuid || r.expected_json)
          .map(r => {
            let expected: Record<string, unknown> | undefined
            if (r.expected_json.trim()) {
              try {
                expected = JSON.parse(r.expected_json)
              } catch {
                throw new Error(`Invalid JSON in expected values`)
              }
            }
            return { document_uuid: r.document_uuid || undefined, expected }
          })
        if (!tcs.length) throw new Error('Add at least one test case to establish a baseline')
        baseline.test_cases = tcs
      } else if (item.item_kind === 'knowledge_base') {
        const qs = kbRows
          .filter(r => r.query.trim())
          .map(r => ({
            query: r.query.trim(),
            expected_answer: r.expected_answer.trim() || undefined,
          }))
        if (!qs.length) throw new Error('Add at least one query to establish a baseline')
        baseline.queries = qs
      } else {
        const inputs = workflowRows
          .filter(r => r.input.trim())
          .map(r => ({
            input: r.input.trim(),
            expected_output: r.expected_output.trim() || undefined,
          }))
        if (!inputs.length) throw new Error('Add at least one regression input to establish a baseline')
        baseline.example_inputs = inputs
      }
      baseline._examiner_curated = true
      baseline._retroactive = true

      const scoreNum = score.trim() ? parseFloat(score) : undefined
      if (scoreNum !== undefined && (isNaN(scoreNum) || scoreNum < 0 || scoreNum > 100)) {
        throw new Error('Score must be a number between 0 and 100')
      }

      const result = await pinRetroactiveBaseline(item.item_kind, item.item_id, {
        baseline,
        score: scoreNum,
      })
      if (result.live_passes_baseline === false) {
        setWarning(
          `Pinned. Soft warning: live config currently scores ${result.live_score != null ? Math.round(result.live_score) + '%' : 'N/A'}, below the new baseline (${result.pinned_score != null ? Math.round(result.pinned_score) + '%' : 'N/A'}). The catalog entry may not currently pass its own baseline.`,
        )
        // Keep dialog open to show warning; user can dismiss
      } else {
        onSaved()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const content = (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        backgroundColor: 'rgba(0,0,0,0.4)',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`${item.official_baseline_pinned_at ? 'Update' : 'Establish'} official baseline`}
        style={{
        background: '#fff', borderRadius: 'var(--workspace-radius-large)', width: '100%', maxWidth: 680,
        maxHeight: '90vh', display: 'flex', flexDirection: 'column',
        boxShadow: 'var(--workspace-shadow-dialog)', margin: "0 var(--workspace-space-16)",
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: "var(--workspace-space-16) var(--workspace-space-20)", borderBottom: "1px solid var(--workspace-border)",
        }}>
          <div>
            <div style={{ fontSize: 'var(--workspace-font-body)', fontWeight: 700, color: '#111' }}>
              {item.official_baseline_pinned_at ? 'Update' : 'Establish'} official baseline
            </div>
            <div style={{ fontSize: 'var(--workspace-font-meta)', color: '#6b7280', marginTop: 'var(--workspace-space-2)' }}>
              Retroactively pin a validation baseline for this {kindLabel(item.item_kind)}: <strong>{item.name}</strong>
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', padding: 'var(--workspace-space-4)' }}>
            <X size={18} />
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: "var(--workspace-space-16) var(--workspace-space-20)", display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-16)' }}>
          {item.official_baseline_pinned_at && (
            <div style={{ fontSize: 'var(--workspace-font-meta)', color: '#92400e', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-8) var(--workspace-space-12)" }}>
              This item already has a pinned baseline ({item.official_baseline_test_case_count} case(s), score {item.official_baseline_score != null ? Math.round(item.official_baseline_score) + '%' : 'unknown'}). Saving will archive the previous one.
            </div>
          )}

          {/* Kind-specific editor */}
          {item.item_kind === 'search_set' && (
            <section>
              <div style={{ fontSize: 'var(--workspace-font-meta)', fontWeight: 700, color: '#111827', marginBottom: 'var(--workspace-space-8)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Test cases
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-8)' }}>
                {extractionRows.map((row, i) => (
                  <div key={i} style={{ border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: 'var(--workspace-space-12)', display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-6)' }}>
                    <div>
                      <label style={labelStyle}>Document UUID</label>
                      <input value={row.document_uuid} onChange={e => {
                        const copy = [...extractionRows]; copy[i] = { ...row, document_uuid: e.target.value }; setExtractionRows(copy)
                      }} style={inputStyle} placeholder="(optional) document UUID" />
                    </div>
                    <div>
                      <label style={labelStyle}>Expected values (JSON)</label>
                      <textarea value={row.expected_json} onChange={e => {
                        const copy = [...extractionRows]; copy[i] = { ...row, expected_json: e.target.value }; setExtractionRows(copy)
                      }} rows={3} style={{ ...inputStyle, resize: 'vertical', fontFamily: 'ui-monospace, monospace' }} placeholder='{"field": "value"}' />
                    </div>
                    <button onClick={() => setExtractionRows(extractionRows.filter((_, j) => j !== i))}
                      style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)', fontSize: 'var(--workspace-font-meta)', color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer' }}>
                      <Trash2 size={12} /> Remove
                    </button>
                  </div>
                ))}
                <button onClick={() => setExtractionRows([...extractionRows, { document_uuid: '', expected_json: '' }])}
                  style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)', fontSize: 'var(--workspace-font-meta)', color: '#374151', background: '#f3f4f6', border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-6) var(--workspace-space-12)", cursor: 'pointer' }}>
                  <Plus size={12} /> Add test case
                </button>
              </div>
            </section>
          )}

          {item.item_kind === 'knowledge_base' && (
            <section>
              <div style={{ fontSize: 'var(--workspace-font-meta)', fontWeight: 700, color: '#111827', marginBottom: 'var(--workspace-space-8)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Queries
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-8)' }}>
                {kbRows.map((row, i) => (
                  <div key={i} style={{ border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: 'var(--workspace-space-12)', display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-6)' }}>
                    <div>
                      <label style={labelStyle}>Query</label>
                      <input value={row.query} onChange={e => {
                        const copy = [...kbRows]; copy[i] = { ...row, query: e.target.value }; setKbRows(copy)
                      }} style={inputStyle} placeholder="What should the KB be able to answer?" />
                    </div>
                    <div>
                      <label style={labelStyle}>Expected answer (optional)</label>
                      <textarea value={row.expected_answer} onChange={e => {
                        const copy = [...kbRows]; copy[i] = { ...row, expected_answer: e.target.value }; setKbRows(copy)
                      }} rows={2} style={{ ...inputStyle, resize: 'vertical' }} />
                    </div>
                    <button onClick={() => setKbRows(kbRows.filter((_, j) => j !== i))}
                      style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)', fontSize: 'var(--workspace-font-meta)', color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer' }}>
                      <Trash2 size={12} /> Remove
                    </button>
                  </div>
                ))}
                <button onClick={() => setKbRows([...kbRows, { query: '', expected_answer: '' }])}
                  style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)', fontSize: 'var(--workspace-font-meta)', color: '#374151', background: '#f3f4f6', border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-6) var(--workspace-space-12)", cursor: 'pointer' }}>
                  <Plus size={12} /> Add query
                </button>
              </div>
            </section>
          )}

          {item.item_kind === 'workflow' && (
            <section>
              <div style={{ fontSize: 'var(--workspace-font-meta)', fontWeight: 700, color: '#111827', marginBottom: 'var(--workspace-space-8)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Regression inputs
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-8)' }}>
                {workflowRows.map((row, i) => (
                  <div key={i} style={{ border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: 'var(--workspace-space-12)', display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-6)' }}>
                    <div>
                      <label style={labelStyle}>Input</label>
                      <textarea value={row.input} onChange={e => {
                        const copy = [...workflowRows]; copy[i] = { ...row, input: e.target.value }; setWorkflowRows(copy)
                      }} rows={2} style={{ ...inputStyle, resize: 'vertical' }} placeholder="A representative input" />
                    </div>
                    <div>
                      <label style={labelStyle}>Expected output (optional)</label>
                      <textarea value={row.expected_output} onChange={e => {
                        const copy = [...workflowRows]; copy[i] = { ...row, expected_output: e.target.value }; setWorkflowRows(copy)
                      }} rows={2} style={{ ...inputStyle, resize: 'vertical' }} />
                    </div>
                    <button onClick={() => setWorkflowRows(workflowRows.filter((_, j) => j !== i))}
                      style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)', fontSize: 'var(--workspace-font-meta)', color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer' }}>
                      <Trash2 size={12} /> Remove
                    </button>
                  </div>
                ))}
                <button onClick={() => setWorkflowRows([...workflowRows, { input: '', expected_output: '' }])}
                  style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)', fontSize: 'var(--workspace-font-meta)', color: '#374151', background: '#f3f4f6', border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-6) var(--workspace-space-12)", cursor: 'pointer' }}>
                  <Plus size={12} /> Add regression input
                </button>
              </div>
            </section>
          )}

          <div>
            <label style={labelStyle}>Baseline reference score (optional, 0–100)</label>
            <input value={score} onChange={e => setScore(e.target.value)} type="number" min="0" max="100" placeholder="e.g. 85" style={{ ...inputStyle, maxWidth: 160 }} />
            <p style={{ fontSize: 'var(--workspace-font-meta)', color: '#9ca3af', marginTop: 'var(--workspace-space-4)' }}>
              Drift monitoring compares the live config's score to this reference. Leave blank if unknown, set it after a real validation run.
            </p>
          </div>

          {warning && (
            <div style={{ padding: "var(--workspace-space-12) var(--workspace-space-12)", borderRadius: 'var(--workspace-radius-small)', background: '#fef3c7', border: '1px solid #fcd34d', fontSize: 'var(--workspace-font-meta)', color: '#78350f', display: 'flex', alignItems: 'flex-start', gap: 'var(--workspace-space-6)' }}>
              <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
              <div>
                <div style={{ fontWeight: 600, marginBottom: 'var(--workspace-space-4)' }}>Baseline pinned with caveat</div>
                <div>{warning}</div>
                <button onClick={onSaved} style={{ marginTop: 'var(--workspace-space-6)', fontSize: 'var(--workspace-font-meta)', fontWeight: 600, color: '#78350f', background: 'none', border: 'none', textDecoration: 'underline', cursor: 'pointer', padding: 0 }}>
                  Dismiss and close
                </button>
              </div>
            </div>
          )}

          {error && (
            <div style={{ padding: "var(--workspace-space-8) var(--workspace-space-12)", borderRadius: 'var(--workspace-radius-small)', background: '#fee2e2', border: '1px solid #fca5a5', fontSize: 'var(--workspace-font-meta)', color: '#991b1b' }}>
              {error}
            </div>
          )}
        </div>

        <div style={{
          padding: "var(--workspace-space-12) var(--workspace-space-20)", borderTop: "1px solid var(--workspace-border)",
          display: 'flex', justifyContent: 'flex-end', gap: 'var(--workspace-space-12)',
        }}>
          <button onClick={onClose} style={{
            padding: "7px var(--workspace-space-16)", borderRadius: 'var(--workspace-radius-small)', border: "1px solid var(--workspace-border)",
            background: '#fff', fontSize: 'var(--workspace-font-control)', fontWeight: 600, cursor: 'pointer', color: '#374151',
          }}>
            Cancel
          </button>
          <button onClick={handleSave} disabled={saving} style={{
            display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-6)',
            padding: "7px var(--workspace-space-20)", borderRadius: 'var(--workspace-radius-small)', border: 'none',
            background: '#111827', color: '#fff', fontSize: 'var(--workspace-font-control)', fontWeight: 600,
            cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.6 : 1,
          }}>
            <Save size={14} />
            {saving ? 'Pinning…' : 'Pin baseline'}
          </button>
        </div>
      </div>
      </FocusTrap>
    </div>
  )

  return createPortal(content, document.body)
}
