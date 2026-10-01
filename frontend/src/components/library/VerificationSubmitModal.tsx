import { usePanelEffect } from '../shared/usePanelEffect'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from '../shared/panelPortal'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { X, ShieldCheck, ChevronRight, ChevronLeft, Upload, Users, Eye } from 'lucide-react'
import { submitForVerification } from '../../api/library'
import { useAuth } from '../../hooks/useAuth'
import { useShareLabel } from '../../lib/catalogLabels'
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
  /** When the caller can share this item with the user's team (no examiner
   *  involved), the first step offers that beside the examiner paths. */
  onShareWithTeam?: () => void
}

// The first step is what you want, not a form. "Get a second pair of eyes"
// is the backend's pending_admin_validation path, promoted from an amber
// opt-out checkbox on the last step to a door on the first one — asking for
// help should feel like a normal thing to want, not an irregularity.
type Intent = 'everyone' | 'help'

// Then one required field. The optional material (how to run it, what to
// look for, example inputs) lives on one step and says it is optional, so
// the shape of the form does not overstate what sharing asks of you.
type Step = 'intent' | 'basics' | 'details' | 'review'
const STEPS: { key: Step; label: string }[] = [
  { key: 'intent', label: 'What do you want?' },
  { key: 'basics', label: 'Basics' },
  { key: 'details', label: 'Details (optional)' },
  { key: 'review', label: 'Review' },
]

export function VerificationSubmitModal({ itemKind, itemId, itemTitle, onClose, onSubmitted, onShareWithTeam }: Props) {
  const { user } = useAuth()
  const [step, setStep] = useState<Step>('intent')
  const [intent, setIntent] = useState<Intent | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const submittingRef = useRef(false)
  const [error, setError] = useState('')
  const errorRef = useRef<HTMLParagraphElement>(null)
  useEffect(() => { if (error && !submitting) errorRef.current?.focus() }, [error, submitting])

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
  const skipValidation = intent === 'help'

  usePanelEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape' && !submittingRef.current) onClose() }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const stepIndex = STEPS.findIndex(s => s.key === step)
  const canGoBack = stepIndex > 0
  const canGoNext = stepIndex < STEPS.length - 1 && (step !== 'intent' || intent !== null)
  const isLastStep = stepIndex === STEPS.length - 1
  const chooseIntent = (i: Intent) => {
    setIntent(i)
    setStep('basics')
  }

  const goNext = () => {
    if (canGoNext) setStep(STEPS[stepIndex + 1].key)
  }
  const goBack = () => {
    if (canGoBack) setStep(STEPS[stepIndex - 1].key)
  }

  const splitLines = (text: string) => text.split('\n').map(s => s.trim()).filter(Boolean)

  const handleSubmit = async () => {
    if (submittingRef.current) return
    submittingRef.current = true
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
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  const kindLabel = itemKind === 'workflow' ? 'Workflow' : itemKind === 'knowledge_base' ? 'Knowledge Base' : 'Extraction'
  const shareLabel = useShareLabel()

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
      <div role="dialog" aria-modal="true" aria-label={shareLabel} className="bg-white rounded-lg shadow-xl max-w-2xl w-full min-w-0 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="shrink-0 flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-green-600" aria-hidden="true" />
            <h3 className="text-base font-semibold text-gray-900">{shareLabel}</h3>
          </div>
          <button type="button" disabled={submitting} onClick={onClose} aria-label="Close" className="p-1 rounded hover:bg-gray-100 text-gray-500">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Step indicator */}
        <div className="shrink-0 flex flex-wrap items-center gap-1 px-5 py-3 bg-gray-50 border-b border-gray-200">
          {STEPS.map((s, i) => (
            <div key={s.key} className="flex items-center gap-1">
              <button
                type="button"
                // Past the first step only once a door is chosen: jumping to
                // Review with no intent would submit as "everyone" unasked.
                disabled={submitting || (intent === null && s.key !== 'intent')}
                aria-current={step === s.key ? 'step' : undefined}
                onClick={() => setStep(s.key)}
                className={`text-xs font-medium px-2 py-1 rounded disabled:opacity-40 disabled:cursor-not-allowed ${
                  step === s.key
                    ? 'bg-gray-900 text-white'
                    : i < stepIndex
                      ? 'text-green-700 hover:bg-green-50'
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
        <div className="flex-1 min-h-0 overflow-y-auto">
        <fieldset disabled={submitting} className="min-w-0 border-0 m-0 p-5 space-y-4">
          <div className="text-xs text-gray-500 flex items-center gap-2 mb-2">
            <span className="px-2 py-0.5 rounded bg-gray-100 text-gray-600">{kindLabel}</span>
            {itemTitle && <span className="font-medium text-gray-700">{itemTitle}</span>}
          </div>

          {step === 'intent' && (
            <div className="space-y-3">
              <p className="text-sm text-gray-700">
                Sharing puts this {kindLabel.toLowerCase()} where colleagues can copy it. It doesn't need to be finished, and the score it carries can be low — it just has to be useful to someone and honest about what it does.
              </p>
              <div className="grid gap-2">
                {onShareWithTeam && (
                  <button
                    type="button"
                    onClick={() => { onClose(); onShareWithTeam() }}
                    className="flex items-start gap-3 rounded-lg border border-gray-200 bg-white p-3.5 text-left hover:border-gray-400 hover:bg-gray-50"
                  >
                    <Users className="h-5 w-5 mt-0.5 text-gray-500 shrink-0" aria-hidden="true" />
                    <span>
                      <span className="block text-sm font-semibold text-gray-900">Share with a team</span>
                      <span className="block text-xs text-gray-600 mt-0.5">A team you belong to — you pick which. No examiner involved.</span>
                    </span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => chooseIntent('everyone')}
                  aria-pressed={intent === 'everyone'}
                  className="flex items-start gap-3 rounded-lg border border-gray-200 bg-white p-3.5 text-left hover:border-gray-400 hover:bg-gray-50"
                >
                  <ShieldCheck className="h-5 w-5 mt-0.5 text-green-600 shrink-0" aria-hidden="true" />
                  <span>
                    <span className="block text-sm font-semibold text-gray-900">Share with everyone — it works for me</span>
                    <span className="block text-xs text-gray-600 mt-0.5">An examiner looks it over and accepts it. Its score, if it has one, travels with it.</span>
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => chooseIntent('help')}
                  aria-pressed={intent === 'help'}
                  className="flex items-start gap-3 rounded-lg border border-gray-200 bg-white p-3.5 text-left hover:border-gray-400 hover:bg-gray-50"
                >
                  <Eye className="h-5 w-5 mt-0.5 text-blue-600 shrink-0" aria-hidden="true" />
                  <span>
                    <span className="block text-sm font-semibold text-gray-900">Get a second pair of eyes</span>
                    <span className="block text-xs text-gray-600 mt-0.5">Ask an examiner to look at it and run a validation for you. Takes a little longer; you'll get a score and notes back.</span>
                  </span>
                </button>
              </div>
            </div>
          )}

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
                  placeholder="Example: Check a sponsor notice for deadline and budget requirements. Describe the task, required document and result someone should expect."
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
              <p className="text-sm text-gray-600">Help others judge whether this fits their task. Include one small example input, its expected result and any limitations. Omit confidential source material.</p>
              <div>
                <label htmlFor="vsm-run-instructions" className="block text-sm font-medium text-gray-700 mb-1">Run Instructions</label>
                <textarea
                  id="vsm-run-instructions"
                  value={runInstructions}
                  onChange={(e) => setRunInstructions(e.target.value)}
                  rows={3}
                  placeholder="Describe the required input and how to run it. Example: Select one sponsor notice, then Run; inspect each deadline against its cited passage."
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

          {step === 'details' && (
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
            <div className="space-y-3 break-words">
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
                    <dd className="text-gray-700 whitespace-pre-wrap break-words">{exampleInputs}</dd>
                  </div>
                )}
                {expectedOutputs && (
                  <div>
                    <dt className="text-xs font-medium text-gray-500 uppercase">Expected Outputs</dt>
                    <dd className="text-gray-700 whitespace-pre-wrap break-words">{expectedOutputs}</dd>
                  </div>
                )}
                {dependencies && (
                  <div>
                    <dt className="text-xs font-medium text-gray-500 uppercase">Dependencies</dt>
                    <dd className="text-gray-700 whitespace-pre-wrap break-words">{dependencies}</dd>
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

              {/* What was chosen on step 1, in one line, with the way back. */}
              <div className="flex items-start justify-between gap-3 rounded-md bg-gray-50 border border-gray-200 px-3.5 py-2.5">
                <span className="text-xs text-gray-700">
                  {skipValidation
                    ? <><span className="font-semibold">Second pair of eyes</span> — an examiner will look it over and run a validation, then get back to you with a score and notes.</>
                    : <><span className="font-semibold">Share with everyone</span> — an examiner looks it over and accepts it. Its current score travels with it.</>}
                </span>
                <button type="button" onClick={() => setStep('intent')} className="text-xs text-gray-600 underline shrink-0">Change</button>
              </div>

              {error && <p ref={errorRef} tabIndex={-1} role="alert" className="text-sm text-red-800 bg-red-50 border border-red-200 rounded-md px-3 py-2">{error}</p>}
            </div>
          )}
        </fieldset>
        </div>

        {/* Footer */}
        <div className="shrink-0 flex flex-wrap items-center justify-between gap-2 px-5 py-4 border-t border-gray-200 bg-white">
          <div>
            {canGoBack && (
              <button
                onClick={goBack}
                disabled={submitting}
                className="flex items-center gap-1 px-3 py-2 text-sm font-medium text-gray-600 hover:text-gray-900"
              >
                <ChevronLeft className="h-4 w-4" />
                Back
              </button>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={onClose}
              disabled={submitting}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
            >
              Cancel
            </button>
            {isLastStep ? (
              <button
                onClick={handleSubmit}
                disabled={submitting || !summary.trim()}
                className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-green-700 rounded-md hover:bg-green-800 disabled:opacity-50"
              >
                <Upload className="h-4 w-4" />
                {submitting ? 'Sending...' : skipValidation ? 'Ask for a look' : shareLabel}
              </button>
            ) : (
              <button
                onClick={goNext}
                disabled={!canGoNext}
                className="flex items-center gap-1 px-4 py-2 text-sm font-medium text-white bg-gray-900 rounded-md hover:bg-gray-800 disabled:opacity-50"
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
