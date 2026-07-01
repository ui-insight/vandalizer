import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { FocusTrap } from 'focus-trap-react'
import { X, ShieldCheck, ChevronRight, ChevronLeft, Upload } from 'lucide-react'
import { submitForVerification } from '../../api/library'
import { useAuth } from '../../hooks/useAuth'
import type { LibraryItemKind } from '../../types/library'

const CATEGORIES = [
  'Compliance & Regulatory',
  'Financial & Budgeting',
  'Research Administration',
  'Contracts & Legal',
  'Human Resources',
  'Operations & Logistics',
  'Data Extraction',
  'Document Review',
  'Other',
]

interface Props {
  itemKind: LibraryItemKind
  itemId: string
  itemTitle?: string
  onClose: () => void
  onSubmitted: () => void
}

type Step = 'basics' | 'details' | 'testing' | 'review'
const STEPS: { key: Step; label: string }[] = [
  { key: 'basics', label: 'Basics' },
  { key: 'details', label: 'Details' },
  { key: 'testing', label: 'Testing' },
  { key: 'review', label: 'Review' },
]

export function VerificationSubmitModal({ itemKind, itemId, itemTitle, onClose, onSubmitted }: Props) {
  const { user } = useAuth()
  const [step, setStep] = useState<Step>('basics')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  // Form data
  const [summary, setSummary] = useState(itemTitle ?? '')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('')
  const [submitterOrg, setSubmitterOrg] = useState('')
  const [runInstructions, setRunInstructions] = useState('')
  const [evaluationNotes, setEvaluationNotes] = useState('')
  const [knownLimitations, setKnownLimitations] = useState('')
  const [exampleInputs, setExampleInputs] = useState('')
  const [expectedOutputs, setExpectedOutputs] = useState('')
  const [dependencies, setDependencies] = useState('')
  const [intendedUseTags, setIntendedUseTags] = useState('')
  const [skipValidation, setSkipValidation] = useState(false)

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const stepIndex = STEPS.findIndex(s => s.key === step)
  const canGoBack = stepIndex > 0
  const canGoNext = stepIndex < STEPS.length - 1
  const isLastStep = stepIndex === STEPS.length - 1

  const goNext = () => {
    if (canGoNext) setStep(STEPS[stepIndex + 1].key)
  }
  const goBack = () => {
    if (canGoBack) setStep(STEPS[stepIndex - 1].key)
  }

  const splitLines = (text: string) => text.split('\n').map(s => s.trim()).filter(Boolean)

  const handleSubmit = async () => {
    setSubmitting(true)
    setError('')
    try {
      await submitForVerification({
        item_kind: itemKind,
        item_id: itemId,
        submitter_name: user?.name || user?.email || undefined,
        submitter_org: submitterOrg.trim() || undefined,
        summary: summary || itemTitle || '',
        description: description || undefined,
        category: category || undefined,
        run_instructions: runInstructions || undefined,
        evaluation_notes: evaluationNotes || undefined,
        known_limitations: knownLimitations || undefined,
        example_inputs: exampleInputs ? splitLines(exampleInputs) : undefined,
        expected_outputs: expectedOutputs ? splitLines(expectedOutputs) : undefined,
        dependencies: dependencies ? splitLines(dependencies) : undefined,
        intended_use_tags: intendedUseTags ? splitLines(intendedUseTags) : undefined,
        skip_validation: skipValidation,
      })
      onSubmitted()
      onClose()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Submission failed')
    } finally {
      setSubmitting(false)
    }
  }

  const kindLabel = itemKind === 'workflow' ? 'Workflow' : itemKind === 'knowledge_base' ? 'Knowledge Base' : 'Extraction'

  return createPortal(
    // Stop propagation at the overlay: this modal is portaled to document.body, but
    // React synthetic events bubble through the React tree (not the DOM tree), so a
    // click on any field would otherwise reach the LibraryItemRow's onClick and
    // navigate to the workflow. See LibraryItemRow row onClick={() => onOpen?.(item)}.
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center p-4"
      style={{ zIndex: 700 }}
      onClick={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div role="dialog" aria-modal="true" aria-label="Submit for Verification" className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-green-600" aria-hidden="true" />
            <h3 className="text-base font-semibold text-gray-900">Submit for Verification</h3>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1 rounded hover:bg-gray-100 text-gray-500">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Step indicator */}
        <div className="flex items-center gap-1 px-5 py-3 bg-gray-50 border-b border-gray-200">
          {STEPS.map((s, i) => (
            <div key={s.key} className="flex items-center gap-1">
              <button
                onClick={() => setStep(s.key)}
                className={`text-xs font-medium px-2 py-1 rounded ${
                  step === s.key
                    ? 'bg-gray-900 text-white'
                    : i < stepIndex
                      ? 'text-green-600 hover:bg-green-50'
                      : 'text-gray-500'
                }`}
              >
                {i + 1}. {s.label}
              </button>
              {i < STEPS.length - 1 && <ChevronRight className="h-3 w-3 text-gray-500" />}
            </div>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          <div className="text-xs text-gray-500 flex items-center gap-2 mb-2">
            <span className="px-2 py-0.5 rounded bg-gray-100 text-gray-600">{kindLabel}</span>
            {itemTitle && <span className="font-medium text-gray-700">{itemTitle}</span>}
          </div>

          {step === 'basics' && (
            <>
              <div>
                <label htmlFor="vsm-summary" className="block text-sm font-medium text-gray-700 mb-1">Summary *</label>
                <input
                  id="vsm-summary"
                  type="text"
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  placeholder="Brief name for this submission"
                  aria-required="true"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
              <div>
                <label htmlFor="vsm-description" className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                <textarea
                  id="vsm-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={4}
                  placeholder="What does this item do? What problem does it solve?"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
              <div>
                <label htmlFor="vsm-category" className="block text-sm font-medium text-gray-700 mb-1">Category</label>
                <select
                  id="vsm-category"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md bg-white focus:outline-none focus:ring-1 focus:ring-gray-400"
                >
                  <option value="">Select a category...</option>
                  {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="vsm-org" className="block text-sm font-medium text-gray-700 mb-1">Your Organization</label>
                <input
                  id="vsm-org"
                  type="text"
                  value={submitterOrg}
                  onChange={(e) => setSubmitterOrg(e.target.value)}
                  placeholder="e.g., University of Idaho"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
            </>
          )}

          {step === 'details' && (
            <>
              <div>
                <label htmlFor="vsm-run-instructions" className="block text-sm font-medium text-gray-700 mb-1">Run Instructions</label>
                <textarea
                  id="vsm-run-instructions"
                  value={runInstructions}
                  onChange={(e) => setRunInstructions(e.target.value)}
                  rows={3}
                  placeholder="How should an examiner test this? What documents work best?"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
              <div>
                <label htmlFor="vsm-evaluation-notes" className="block text-sm font-medium text-gray-700 mb-1">Evaluation Notes</label>
                <textarea
                  id="vsm-evaluation-notes"
                  value={evaluationNotes}
                  onChange={(e) => setEvaluationNotes(e.target.value)}
                  rows={3}
                  placeholder="What should the reviewer pay attention to when evaluating quality?"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
              <div>
                <label htmlFor="vsm-known-limitations" className="block text-sm font-medium text-gray-700 mb-1">Known Limitations</label>
                <textarea
                  id="vsm-known-limitations"
                  value={knownLimitations}
                  onChange={(e) => setKnownLimitations(e.target.value)}
                  rows={2}
                  placeholder="Any edge cases, document types, or scenarios where this doesn't work well?"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
              <div>
                <label htmlFor="vsm-dependencies" className="block text-sm font-medium text-gray-700 mb-1">Dependencies</label>
                <textarea
                  id="vsm-dependencies"
                  value={dependencies}
                  onChange={(e) => setDependencies(e.target.value)}
                  rows={2}
                  placeholder="One per line. Other items this depends on (e.g., a knowledge base, a specific extraction)"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
            </>
          )}

          {step === 'testing' && (
            <>
              <div>
                <label htmlFor="vsm-example-inputs" className="block text-sm font-medium text-gray-700 mb-1">Example Inputs</label>
                <textarea
                  id="vsm-example-inputs"
                  value={exampleInputs}
                  onChange={(e) => setExampleInputs(e.target.value)}
                  rows={3}
                  placeholder="One per line. Example document descriptions or text snippets that work well"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
              <div>
                <label htmlFor="vsm-expected-outputs" className="block text-sm font-medium text-gray-700 mb-1">Expected Outputs</label>
                <textarea
                  id="vsm-expected-outputs"
                  value={expectedOutputs}
                  onChange={(e) => setExpectedOutputs(e.target.value)}
                  rows={3}
                  placeholder="One per line. What the examiner should expect to see in results"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
              <div>
                <label htmlFor="vsm-intended-use-tags" className="block text-sm font-medium text-gray-700 mb-1">Intended Use Tags</label>
                <textarea
                  id="vsm-intended-use-tags"
                  value={intendedUseTags}
                  onChange={(e) => setIntendedUseTags(e.target.value)}
                  rows={2}
                  placeholder="One per line. Tags like: research-admin, compliance, hr, finance"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
            </>
          )}

          {step === 'review' && (
            <div className="space-y-3">
              <h4 className="text-sm font-semibold text-gray-900">Review your submission</h4>
              <dl className="space-y-2 text-sm">
                <div>
                  <dt className="text-xs font-medium text-gray-500 uppercase">Summary</dt>
                  <dd className="text-gray-700">{summary || itemTitle}</dd>
                </div>
                {description && (
                  <div>
                    <dt className="text-xs font-medium text-gray-500 uppercase">Description</dt>
                    <dd className="text-gray-700 whitespace-pre-wrap">{description}</dd>
                  </div>
                )}
                {category && (
                  <div>
                    <dt className="text-xs font-medium text-gray-500 uppercase">Category</dt>
                    <dd className="text-gray-700">{category}</dd>
                  </div>
                )}
                {submitterOrg.trim() && (
                  <div>
                    <dt className="text-xs font-medium text-gray-500 uppercase">Organization</dt>
                    <dd className="text-gray-700">{submitterOrg}</dd>
                  </div>
                )}
                {runInstructions && (
                  <div>
                    <dt className="text-xs font-medium text-gray-500 uppercase">Run Instructions</dt>
                    <dd className="text-gray-700 whitespace-pre-wrap">{runInstructions}</dd>
                  </div>
                )}
                {evaluationNotes && (
                  <div>
                    <dt className="text-xs font-medium text-gray-500 uppercase">Evaluation Notes</dt>
                    <dd className="text-gray-700 whitespace-pre-wrap">{evaluationNotes}</dd>
                  </div>
                )}
                {knownLimitations && (
                  <div>
                    <dt className="text-xs font-medium text-gray-500 uppercase">Known Limitations</dt>
                    <dd className="text-gray-700 whitespace-pre-wrap">{knownLimitations}</dd>
                  </div>
                )}
                {exampleInputs && (
                  <div>
                    <dt className="text-xs font-medium text-gray-500 uppercase">Example Inputs</dt>
                    <dd className="text-gray-700">{splitLines(exampleInputs).length} item(s)</dd>
                  </div>
                )}
                {expectedOutputs && (
                  <div>
                    <dt className="text-xs font-medium text-gray-500 uppercase">Expected Outputs</dt>
                    <dd className="text-gray-700">{splitLines(expectedOutputs).length} item(s)</dd>
                  </div>
                )}
                {intendedUseTags && (
                  <div>
                    <dt className="text-xs font-medium text-gray-500 uppercase">Intended Use Tags</dt>
                    <dd className="flex flex-wrap gap-1 mt-1">
                      {splitLines(intendedUseTags).map((tag, i) => (
                        <span key={i} className="text-xs px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                          {tag}
                        </span>
                      ))}
                    </dd>
                  </div>
                )}
              </dl>

              {/* Submit-without-validation opt-in (Phase B) */}
              <label className="flex items-start gap-2 cursor-pointer rounded-md bg-amber-50 border border-amber-200 px-3.5 py-2.5">
                <input
                  type="checkbox"
                  checked={skipValidation}
                  onChange={(e) => setSkipValidation(e.target.checked)}
                  className="mt-0.5"
                />
                <span>
                  <span className="block text-xs font-semibold text-amber-900">
                    Submit without validation — request reviewer help
                  </span>
                  <span className="block text-[11px] leading-snug text-amber-800 mt-0.5">
                    Reviewer will establish a validation baseline before approval. May take longer to review and could be returned for rework. Most submissions should be validated by the submitter first.
                  </span>
                </span>
              </label>

              {error && <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">{error}</p>}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-4 border-t border-gray-200">
          <div>
            {canGoBack && (
              <button
                onClick={goBack}
                className="flex items-center gap-1 px-3 py-2 text-sm font-medium text-gray-600 hover:text-gray-900"
              >
                <ChevronLeft className="h-4 w-4" />
                Back
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
            >
              Cancel
            </button>
            {isLastStep ? (
              <button
                onClick={handleSubmit}
                disabled={submitting || !summary.trim()}
                className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700 disabled:opacity-50"
              >
                <Upload className="h-4 w-4" />
                {submitting ? 'Submitting...' : skipValidation ? 'Submit (reviewer will validate)' : 'Submit for Verification'}
              </button>
            ) : (
              <button
                onClick={goNext}
                className="flex items-center gap-1 px-4 py-2 text-sm font-medium text-white bg-gray-900 rounded-md hover:bg-gray-800"
              >
                Next
                <ChevronRight className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      </div>
      </FocusTrap>
    </div>,
    document.body,
  )
}
