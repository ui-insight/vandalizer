import { useState } from 'react'
import { X, ShieldCheck, ChevronRight, ChevronLeft, Upload } from 'lucide-react'
import { submitForVerification } from '../../api/library'
import type { LibraryItem } from '../../types/library'

interface Props {
  item: LibraryItem
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

export function VerificationSubmitModal({ item, onClose, onSubmitted }: Props) {
  const [step, setStep] = useState<Step>('basics')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  // Form data
  const [summary, setSummary] = useState(item.name)
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('')
  const [runInstructions, setRunInstructions] = useState('')
  const [evaluationNotes, setEvaluationNotes] = useState('')
  const [knownLimitations, setKnownLimitations] = useState('')
  const [exampleInputs, setExampleInputs] = useState('')
  const [expectedOutputs, setExpectedOutputs] = useState('')
  const [dependencies, setDependencies] = useState('')
  const [intendedUseTags, setIntendedUseTags] = useState('')

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
        item_kind: item.kind,
        item_id: item.item_id,
        summary: summary || item.name,
        description: description || undefined,
        category: category || undefined,
        run_instructions: runInstructions || undefined,
        evaluation_notes: evaluationNotes || undefined,
        known_limitations: knownLimitations || undefined,
        example_inputs: exampleInputs ? splitLines(exampleInputs) : undefined,
        expected_outputs: expectedOutputs ? splitLines(expectedOutputs) : undefined,
        dependencies: dependencies ? splitLines(dependencies) : undefined,
        intended_use_tags: intendedUseTags ? splitLines(intendedUseTags) : undefined,
      })
      onSubmitted()
      onClose()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Submission failed')
    } finally {
      setSubmitting(false)
    }
  }

  const kindLabel = item.kind === 'workflow' ? 'Workflow' : item.kind === 'knowledge_base' ? 'Knowledge Base' : 'Extraction'

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-green-600" />
            <h3 className="text-base font-semibold text-gray-900">Submit for Verification</h3>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100 text-gray-500">
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
                      : 'text-gray-400'
                }`}
              >
                {i + 1}. {s.label}
              </button>
              {i < STEPS.length - 1 && <ChevronRight className="h-3 w-3 text-gray-300" />}
            </div>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          <div className="text-xs text-gray-500 flex items-center gap-2 mb-2">
            <span className="px-2 py-0.5 rounded bg-gray-100 text-gray-600">{kindLabel}</span>
            <span className="font-medium text-gray-700">{item.name}</span>
          </div>

          {step === 'basics' && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Summary *</label>
                <input
                  type="text"
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  placeholder="Brief name for this submission"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={4}
                  placeholder="What does this item do? What problem does it solve?"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
                <input
                  type="text"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  placeholder="e.g., NSF proposals, HR documents, grant budgets"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
            </>
          )}

          {step === 'details' && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Run Instructions</label>
                <textarea
                  value={runInstructions}
                  onChange={(e) => setRunInstructions(e.target.value)}
                  rows={3}
                  placeholder="How should an examiner test this? What documents work best?"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Evaluation Notes</label>
                <textarea
                  value={evaluationNotes}
                  onChange={(e) => setEvaluationNotes(e.target.value)}
                  rows={3}
                  placeholder="What should the reviewer pay attention to when evaluating quality?"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Known Limitations</label>
                <textarea
                  value={knownLimitations}
                  onChange={(e) => setKnownLimitations(e.target.value)}
                  rows={2}
                  placeholder="Any edge cases, document types, or scenarios where this doesn't work well?"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Dependencies</label>
                <textarea
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
                <label className="block text-sm font-medium text-gray-700 mb-1">Example Inputs</label>
                <textarea
                  value={exampleInputs}
                  onChange={(e) => setExampleInputs(e.target.value)}
                  rows={3}
                  placeholder="One per line. Example document descriptions or text snippets that work well"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Expected Outputs</label>
                <textarea
                  value={expectedOutputs}
                  onChange={(e) => setExpectedOutputs(e.target.value)}
                  rows={3}
                  placeholder="One per line. What the examiner should expect to see in results"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Intended Use Tags</label>
                <textarea
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
                  <dt className="text-xs font-medium text-gray-400 uppercase">Summary</dt>
                  <dd className="text-gray-700">{summary || item.name}</dd>
                </div>
                {description && (
                  <div>
                    <dt className="text-xs font-medium text-gray-400 uppercase">Description</dt>
                    <dd className="text-gray-700 whitespace-pre-wrap">{description}</dd>
                  </div>
                )}
                {category && (
                  <div>
                    <dt className="text-xs font-medium text-gray-400 uppercase">Category</dt>
                    <dd className="text-gray-700">{category}</dd>
                  </div>
                )}
                {runInstructions && (
                  <div>
                    <dt className="text-xs font-medium text-gray-400 uppercase">Run Instructions</dt>
                    <dd className="text-gray-700 whitespace-pre-wrap">{runInstructions}</dd>
                  </div>
                )}
                {evaluationNotes && (
                  <div>
                    <dt className="text-xs font-medium text-gray-400 uppercase">Evaluation Notes</dt>
                    <dd className="text-gray-700 whitespace-pre-wrap">{evaluationNotes}</dd>
                  </div>
                )}
                {knownLimitations && (
                  <div>
                    <dt className="text-xs font-medium text-gray-400 uppercase">Known Limitations</dt>
                    <dd className="text-gray-700 whitespace-pre-wrap">{knownLimitations}</dd>
                  </div>
                )}
                {exampleInputs && (
                  <div>
                    <dt className="text-xs font-medium text-gray-400 uppercase">Example Inputs</dt>
                    <dd className="text-gray-700">{splitLines(exampleInputs).length} item(s)</dd>
                  </div>
                )}
                {expectedOutputs && (
                  <div>
                    <dt className="text-xs font-medium text-gray-400 uppercase">Expected Outputs</dt>
                    <dd className="text-gray-700">{splitLines(expectedOutputs).length} item(s)</dd>
                  </div>
                )}
                {intendedUseTags && (
                  <div>
                    <dt className="text-xs font-medium text-gray-400 uppercase">Intended Use Tags</dt>
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
                {submitting ? 'Submitting...' : 'Submit for Verification'}
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
    </div>
  )
}
