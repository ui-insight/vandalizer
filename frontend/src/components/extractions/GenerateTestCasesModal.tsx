/**
 * Auto-generate test cases from documents — Phase 1B step 1 of the wizard
 * (used directly today; folded into the wizard in Phase 1C).
 *
 * Flow: pick documents → generate proposals → review/edit expected values →
 * approve and save. The user is in the loop for every saved test case, so
 * we never bake "extract once" bias into ground truth.
 */
import { createPortal } from '../shared/panelPortal'
import { useState } from 'react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { X, Loader2, FileText, Check, AlertCircle } from 'lucide-react'
import {
  generateTestCaseProposals,
  approveTestCaseProposals,
  type ProposedTestCase,
  type TestCaseCoverage,
} from '../../api/extractions'
import { DocumentPickerDialog } from '../shared/DocumentPickerDialog'
import { useToast } from '../../contexts/ToastContext'

interface Props {
  searchSetUuid: string
  onClose: () => void
  /** Called after proposals are approved + persisted. */
  onSaved: () => void
}

type Step = 'pick' | 'generating' | 'review'

const COVERAGE_LABELS: Record<TestCaseCoverage, { label: string; description: string }> = {
  quick: { label: 'Quick', description: 'up to 3 cases: fastest, lowest cost' },
  standard: { label: 'Standard', description: 'up to 5 cases: recommended for most extractions' },
  exhaustive: { label: 'Exhaustive', description: 'up to 10 cases: best coverage, highest cost' },
}

export function GenerateTestCasesModal({ searchSetUuid, onClose, onSaved }: Props) {
  const { toast } = useToast()
  const [step, setStep] = useState<Step>('pick')
  const [coverage, setCoverage] = useState<TestCaseCoverage>('standard')
  const [showPicker, setShowPicker] = useState(false)
  const [errors, setErrors] = useState<Array<{ document_uuid: string; reason: string }>>([])
  const [proposals, setProposals] = useState<ProposedTestCase[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [saving, setSaving] = useState(false)

  const handleDocumentsPicked = async (docs: { uuid: string; title: string }[]) => {
    setShowPicker(false)
    if (docs.length === 0) return
    setStep('generating')
    setErrors([])
    try {
      const result = await generateTestCaseProposals(
        searchSetUuid,
        docs.map(d => d.uuid),
        coverage,
      )
      setProposals(result.proposals)
      setErrors(result.errors)
      // Default: all proposals approved (the "eyeball + approve" pattern)
      setSelectedIds(new Set(result.proposals.map(p => p.proposal_id)))
      setStep('review')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Generation failed', 'error')
      setStep('pick')
    }
  }

  const handleApprove = async () => {
    const approved = proposals.filter(p => selectedIds.has(p.proposal_id))
    if (approved.length === 0) {
      toast('Select at least one proposal to save', 'info')
      return
    }
    setSaving(true)
    try {
      const result = await approveTestCaseProposals(searchSetUuid, approved)
      toast(
        `Saved ${result.count} test case${result.count === 1 ? '' : 's'}`,
        'success',
      )
      onSaved()
      onClose()
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to save test cases', 'error')
    } finally {
      setSaving(false)
    }
  }

  const updateProposalValue = (proposalId: string, field: string, value: string) => {
    setProposals(prev => prev.map(p =>
      p.proposal_id === proposalId
        ? { ...p, expected_values: { ...p.expected_values, [field]: value } }
        : p
    ))
  }

  const toggleSelected = (proposalId: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(proposalId)) next.delete(proposalId)
      else next.add(proposalId)
      return next
    })
  }

  return createPortal(
    <>
      <div style={{
        position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}>
        <FocusTrap active={!showPicker} focusTrapOptions={{ escapeDeactivates: false, allowOutsideClick: true, initialFocus: '#generate-test-cases-title' }}>
        <div role="dialog" aria-modal="true" aria-labelledby="generate-test-cases-title" onKeyDown={event => {
          if (event.key === 'Escape' && !showPicker) { event.preventDefault(); event.stopPropagation(); onClose() }
        }} style={{
          width: step === 'review' ? 720 : 480,
          maxWidth: 'calc(100vw - 24px)',
          maxHeight: '90vh', overflowY: 'auto',
          padding: 22, backgroundColor: '#fff',
          border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-large)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', marginBottom: 'var(--workspace-space-12)' }}>
            <h3 id="generate-test-cases-title" tabIndex={-1} style={{ margin: 0, fontSize: 'var(--workspace-font-card-title)', color: '#1f2937' }}>
              {step === 'review' ? 'Review proposed test cases' : 'Generate test cases'}
            </h3>
            <button
              onClick={onClose} aria-label="Close test case generation"
              style={{ marginLeft: 'auto', minWidth: 36, minHeight: 'var(--workspace-control-height)', flexShrink: 0, display: 'grid', placeItems: 'center', background: 'transparent', border: 'none', cursor: 'pointer', padding: 'var(--workspace-space-2)', color: 'var(--workspace-muted)' }}
            >
              <X size={18} />
            </button>
          </div>

          {step === 'pick' && (
            <PickStep
              coverage={coverage}
              onCoverage={setCoverage}
              onPick={() => setShowPicker(true)}
            />
          )}

          {step === 'generating' && (
            <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--workspace-muted)' }}>
              <Loader2 size={32} style={{ animation: 'spin 1s linear infinite', color: 'var(--workspace-info)' }} />
              <div style={{ marginTop: 'var(--workspace-space-12)', fontSize: 'var(--workspace-font-control)' }}>Generating proposals…</div>
            </div>
          )}

          {step === 'review' && (
            <ReviewStep
              proposals={proposals}
              selectedIds={selectedIds}
              errors={errors}
              onToggleSelected={toggleSelected}
              onUpdateValue={updateProposalValue}
              onSelectAll={() => setSelectedIds(new Set(proposals.map(p => p.proposal_id)))}
              onSelectNone={() => setSelectedIds(new Set())}
              onApprove={handleApprove}
              onCancel={onClose}
              saving={saving}
            />
          )}
        </div>
        </FocusTrap>
      </div>

      {showPicker && (
        <DocumentPickerDialog
          excludeUuids={[]}
          onClose={() => setShowPicker(false)}
          onSelect={handleDocumentsPicked}
        />
      )}
    </>, document.body
  )
}

function PickStep({
  coverage, onCoverage, onPick,
}: {
  coverage: TestCaseCoverage
  onCoverage: (c: TestCaseCoverage) => void
  onPick: () => void
}) {
  return (
    <div>
      <p style={{ fontSize: 'var(--workspace-font-control)', color: '#4b5563', lineHeight: 1.6, marginBottom: 'var(--workspace-space-16)' }}>
        Pick documents to extract from. We'll propose expected values for each, and you review and
        edit before they're saved as test cases. Nothing is saved until you approve.
      </p>
      <div style={{ marginBottom: 'var(--workspace-space-16)' }}>
        <div style={{ fontSize: 'var(--workspace-font-meta)', fontWeight: 600, color: '#374151', marginBottom: 'var(--workspace-space-8)' }}>
          Coverage
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-6)' }}>
          {(Object.keys(COVERAGE_LABELS) as TestCaseCoverage[]).map(c => {
            const active = coverage === c
            return (
              <button
                key={c}
                onClick={() => onCoverage(c)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-12)',
                  padding: "var(--workspace-space-8) var(--workspace-space-12)", textAlign: 'left',
                  backgroundColor: active ? 'var(--workspace-selected)' : '#f9fafb',
                  border: '1px solid ' + (active ? 'var(--workspace-accent-ink)' : '#e5e7eb'),
                  borderRadius: 'var(--workspace-radius-small)', cursor: 'pointer', fontFamily: 'inherit',
                }}
              >
                <span style={{
                  width: 14, height: 14, borderRadius: '50%',
                  border: '2px solid ' + (active ? 'var(--workspace-accent-ink)' : 'var(--workspace-border)'),
                  backgroundColor: active ? 'var(--highlight-color, #eab308)' : 'transparent',
                  flexShrink: 0,
                }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 'var(--workspace-font-control)', fontWeight: 600, color: '#1f2937' }}>{COVERAGE_LABELS[c].label}</div>
                  <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>{COVERAGE_LABELS[c].description}</div>
                </div>
              </button>
            )
          })}
        </div>
      </div>
      <button
        onClick={onPick}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-6)',
          padding: "var(--workspace-space-8) var(--workspace-space-16)", fontSize: 'var(--workspace-font-control)', fontWeight: 600, fontFamily: 'inherit',
          color: 'var(--workspace-text)',
          background: 'var(--workspace-canvas)',
          border: '1px solid var(--workspace-accent-ink)',
          borderRadius: 'var(--workspace-radius-small)', cursor: 'pointer',
        }}
      >
        <FileText size={14} />
        Pick documents
      </button>
    </div>
  )
}

function ReviewStep({
  proposals, selectedIds, errors,
  onToggleSelected, onUpdateValue, onSelectAll, onSelectNone, onApprove, onCancel, saving,
}: {
  proposals: ProposedTestCase[]
  selectedIds: Set<string>
  errors: Array<{ document_uuid: string; reason: string }>
  onToggleSelected: (id: string) => void
  onUpdateValue: (id: string, field: string, value: string) => void
  onSelectAll: () => void
  onSelectNone: () => void
  onApprove: () => void
  onCancel: () => void
  saving: boolean
}) {
  if (proposals.length === 0 && errors.length > 0) {
    return (
      <div>
        <div style={{
          display: 'flex', alignItems: 'flex-start', gap: 'var(--workspace-space-8)',
          padding: 'var(--workspace-space-12)', marginBottom: 'var(--workspace-space-16)',
          background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 'var(--workspace-radius-small)',
        }}>
          <AlertCircle size={14} style={{ color: 'var(--workspace-danger)', flexShrink: 0, marginTop: 'var(--workspace-space-2)' }} />
          <div style={{ fontSize: 'var(--workspace-font-meta)', color: '#7f1d1d' }}>
            <div style={{ fontWeight: 600, marginBottom: 'var(--workspace-space-4)' }}>No proposals could be generated.</div>
            {errors.map((e, i) => (
              <div key={i}>{e.reason}</div>
            ))}
          </div>
        </div>
        <button onClick={onCancel} style={cancelBtnStyle}>Close</button>
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', marginBottom: 'var(--workspace-space-12)', fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
        <span><strong style={{ color: '#1f2937' }}>{selectedIds.size}</strong> of {proposals.length} selected</span>
        <button
          onClick={onSelectAll}
          style={{ ...linkBtnStyle, marginLeft: 'auto' }}
        >
          Select all
        </button>
        <button onClick={onSelectNone} style={linkBtnStyle}>Select none</button>
      </div>

      {errors.length > 0 && (
        <div style={{
          display: 'flex', alignItems: 'flex-start', gap: 'var(--workspace-space-8)',
          padding: 'var(--workspace-space-8)', marginBottom: 'var(--workspace-space-12)',
          background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 'var(--workspace-radius-small)',
          fontSize: 'var(--workspace-font-meta)', color: '#78350f',
        }}>
          <AlertCircle size={12} style={{ color: 'var(--workspace-warning)', flexShrink: 0, marginTop: 'var(--workspace-space-2)' }} />
          <div>
            {errors.length} document{errors.length === 1 ? '' : 's'} couldn't be processed.
          </div>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-12)', maxHeight: 420, overflowY: 'auto' }}>
        {proposals.map(p => {
          const selected = selectedIds.has(p.proposal_id)
          return (
            <div
              key={p.proposal_id}
              style={{
                padding: 'var(--workspace-space-12)',
                background: selected ? '#fff' : '#f9fafb',
                border: '1px solid ' + (selected ? 'var(--workspace-accent-ink)' : '#e5e7eb'),
                borderRadius: 'var(--workspace-radius-small)',
                opacity: selected ? 1 : 0.6,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', marginBottom: 'var(--workspace-space-12)' }}>
                <input
                  type="checkbox"
                  checked={selected}
                  onChange={() => onToggleSelected(p.proposal_id)}
                  style={{ cursor: 'pointer' }}
                />
                <div style={{ fontSize: 'var(--workspace-font-control)', fontWeight: 600, color: '#1f2937', flex: 1 }}>{p.label}</div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 'var(--workspace-space-6)', fontSize: 'var(--workspace-font-meta)' }}>
                {Object.entries(p.expected_values).map(([field, value]) => (
                  <Row
                    key={field}
                    field={field}
                    value={value}
                    disabled={!selected}
                    onChange={v => onUpdateValue(p.proposal_id, field, v)}
                  />
                ))}
              </div>
            </div>
          )
        })}
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--workspace-space-8)', marginTop: 'var(--workspace-space-16)' }}>
        <button onClick={onCancel} disabled={saving} style={cancelBtnStyle}>Cancel</button>
        <button
          onClick={onApprove}
          disabled={saving || selectedIds.size === 0}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-6)',
            padding: "var(--workspace-space-8) var(--workspace-space-16)", fontSize: 'var(--workspace-font-control)', fontWeight: 600, fontFamily: 'inherit',
            color: 'var(--workspace-text)',
            background: saving || selectedIds.size === 0
              ? '#9ca3af'
              : 'var(--workspace-canvas)',
            border: '1px solid ' + (saving || selectedIds.size === 0 ? 'var(--workspace-border)' : 'var(--workspace-accent-ink)'),
            borderRadius: 'var(--workspace-radius-small)',
            cursor: saving || selectedIds.size === 0 ? 'not-allowed' : 'pointer',
          }}
        >
          {saving ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Check size={14} />}
          {saving ? 'Saving…' : `Save ${selectedIds.size} test case${selectedIds.size === 1 ? '' : 's'}`}
        </button>
      </div>
    </div>
  )
}

function Row({
  field, value, disabled, onChange,
}: { field: string; value: string; disabled: boolean; onChange: (v: string) => void }) {
  return (
    <>
      <div style={{ color: 'var(--workspace-muted)', alignSelf: 'center' }}>{field}:</div>
      <input
        value={value}
        disabled={disabled}
        onChange={e => onChange(e.target.value)}
        placeholder="(empty)"
        aria-label={`Expected value for ${field}`}
        style={{
          padding: "var(--workspace-space-4) var(--workspace-space-8)", fontSize: 'var(--workspace-font-meta)', fontFamily: 'inherit',
          color: '#1f2937',
          background: disabled ? '#f3f4f6' : '#fff',
          border: '1px solid var(--workspace-border)',
          borderRadius: 'var(--workspace-radius-small)',
        }}
      />
    </>
  )
}

const cancelBtnStyle: React.CSSProperties = {
  padding: "var(--workspace-space-8) var(--workspace-space-16)", fontSize: 'var(--workspace-font-control)', fontWeight: 500, fontFamily: 'inherit',
  color: '#374151', background: '#fff',
  border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-small)', cursor: 'pointer',
}

const linkBtnStyle: React.CSSProperties = {
  padding: "var(--workspace-space-2) var(--workspace-space-8)", fontSize: 'var(--workspace-font-meta)', fontFamily: 'inherit',
  color: 'var(--workspace-info)', background: 'transparent', border: 'none',
  cursor: 'pointer', textDecoration: 'underline',
}
