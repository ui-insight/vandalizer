import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { getAutomaticReview, getAutomaticReviews } from '../../api/certification'
import type { AutomaticReviewStatus, SavedAutomaticReview, SavedAutomaticReviewList } from '../../types/certification'

const labels: Record<AutomaticReviewStatus, string> = {
  prepared: 'Awaiting assessment', evaluating: 'No final result yet', requirements_supported: 'Draft requirements supported',
  revision_required: 'Revision needed', grading_unavailable: 'Assessment unavailable',
}
const verdicts = { supported: 'Supported by saved evidence', contradicted: 'Correction needed', unclear: 'Evidence needs clarification', not_assessed: 'Not assessed' }
const button = 'min-h-11 min-w-0 max-w-full rounded-lg border border-gray-300 bg-white px-1 py-2 text-left text-sm font-medium text-gray-900 [overflow-wrap:anywhere] sm:px-4'

function savedTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Date unavailable' : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function SavedAutomaticReviews({ enrollmentId, moduleId, initialAttemptId, onOpenWork, workNavigationDisabled = false }: {
  enrollmentId: string; moduleId: string; initialAttemptId?: string
  onOpenWork?: (review: SavedAutomaticReview) => void; workNavigationDisabled?: boolean
}) {
  const [open, setOpen] = useState(!!initialAttemptId)
  const [list, setList] = useState<SavedAutomaticReviewList | null>(null)
  const [selected, setSelected] = useState<SavedAutomaticReview | null>(null)
  const [reference, setReference] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const requests = useRef(0)
  const openButton = useRef<HTMLButtonElement>(null)
  const result = useRef<HTMLDivElement>(null)
  const focusResult = useRef(false), focusOpener = useRef(false)
  useEffect(() => () => { requests.current++ }, [enrollmentId, moduleId])
  async function loadList() {
    const request = ++requests.current
    setOpen(true); setBusy(true); setSelected(null); setError(''); setList(null)
    try {
      const value = await getAutomaticReviews(enrollmentId, moduleId)
      if (request !== requests.current) return
      if (value.enrollment_id !== enrollmentId || value.module_id !== moduleId
        || value.attempts.some(item => item.enrollment_id !== enrollmentId || item.module_id !== moduleId || !labels[item.status])) throw new Error('Identity mismatch')
      setList(value)
    } catch { if (request === requests.current) setError('Saved assessments could not be loaded for this course. Refresh to check again.') }
    finally { if (request === requests.current) setBusy(false) }
  }
  const inspect = useCallback(async (attemptId: string) => {
    const request = ++requests.current
    setSelected(null); setError(''); setBusy(true)
    try {
      const value = await getAutomaticReview(enrollmentId, attemptId)
      if (request !== requests.current) return
      if (value.attempt_id !== attemptId || value.enrollment_id !== enrollmentId || value.module_id !== moduleId
        || !labels[value.status] || (moduleId === 'governance' ? value.assessment_kind !== 'governance_capstone_review_draft' || !/^[a-f0-9]{32}$/.test(value.run_id || '') || !/^[a-f0-9]{32}$/.test(value.governance_review_submission_id || '') : moduleId === 'batch_processing' ? value.assessment_kind !== 'bounded_batch_review_draft' || !/^[a-f0-9]{32}$/.test(value.run_id || '') || !/^[a-f0-9]{32}$/.test(value.batch_review_submission_id || '') : moduleId === 'validation_qa' ? value.assessment_kind !== 'validation_suite_review_draft' || !/^[a-f0-9]{32}$/.test(value.run_id || '') || !/^[a-f0-9]{32}$/.test(value.validation_review_submission_id || '') : moduleId === 'output_delivery' ? value.assessment_kind !== 'output_workflow_review_draft' || !/^[a-f0-9]{32}$/.test(value.run_id || '') || !/^[a-f0-9]{32}$/.test(value.output_review_submission_id || '') : moduleId === 'advanced_nodes' ? value.assessment_kind !== 'budget_workflow_review_draft' || !/^[a-f0-9]{32}$/.test(value.run_id || '') || !/^[a-f0-9]{32}$/.test(value.budget_review_submission_id || '') : moduleId === 'multi_step' ? value.assessment_kind !== 'connected_workflow_review_draft' || !/^[a-f0-9]{32}$/.test(value.run_id || '') || !/^[a-f0-9]{32}$/.test(value.connected_review_submission_id || '') : moduleId === 'workflow_design' ? value.assessment_kind !== 'workflow_design_review_draft' || value.run_id !== null || !/^[a-f0-9]{32}$/.test(value.workflow_design_submission_id || '') : moduleId === 'process_mapping' ? value.assessment_kind !== 'process_design_review_draft' || value.run_id !== null || !/^[a-f0-9]{32}$/.test(value.process_submission_id || '') : value.assessment_kind !== 'practical_review_draft' || !/^[a-f0-9]{32}$/.test(value.run_id || '')) || value.credit_awarded !== false
        || value.module_completion_eligible !== false || value.staff_review_required !== false
        || value.can_request_review !== false || value.can_retry_review !== false) throw new Error('Identity mismatch')
      focusResult.current = true; setSelected(value)
    } catch { if (request === requests.current) setError('This saved assessment could not be opened for this course. Check its reference or refresh the list.') }
    finally { if (request === requests.current) setBusy(false) }
  }, [enrollmentId, moduleId])
  useEffect(() => { if (initialAttemptId) void inspect(initialAttemptId) }, [initialAttemptId, inspect])
  useLayoutEffect(() => {
    if (selected && focusResult.current && result.current) { focusResult.current = false; result.current.focus() }
    if (!open && focusOpener.current && openButton.current) { focusOpener.current = false; openButton.current.focus() }
  }, [selected, open])
  function close() {
    requests.current++; focusResult.current = false; focusOpener.current = true
    setOpen(false); setSelected(null); setList(null); setError(''); setBusy(false)
  }
  return <section className="min-w-0 space-y-3 border-t border-gray-200 pt-4 [overflow-wrap:anywhere] sm:rounded-lg sm:border sm:p-4" aria-label="Saved automatic assessments">
    <h4 className="text-base font-semibold text-gray-900">Saved automatic assessments</h4>
    <p className="text-sm text-gray-700">Read feedback for your saved work. These draft assessments do not award XP or certification.</p>
    {!open ? <button ref={openButton} type="button" className={button} onClick={loadList}>View saved assessments</button> : <>
      <div className="flex flex-wrap gap-2"><button type="button" className={button} onClick={loadList}>Refresh saved assessments</button>
        <button type="button" className={button} onClick={close}>Close assessments</button></div>
      {busy && <p role="status" className="text-sm text-gray-700">Loading saved assessment…</p>}
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      {list && <>
        {!list.attempts.length && <p className="text-sm text-gray-700">No saved assessments are available for this module yet.</p>}
        <ul className="space-y-2">{list.attempts.map((item, index) => <li key={item.attempt_id}>
          <button type="button" className={`${button} w-full`} onClick={() => inspect(item.attempt_id)}>
            Assessment {index + 1} · {labels[item.status]}
            <span className="mt-1 block text-xs text-gray-600">Saved {savedTime(item.prepared_at)}</span>
          </button>
        </li>)}</ul>
        {list.older_attempts_available && <p className="text-sm text-gray-700">Only recent assessments are listed. You can open older work by its full reference.</p>}
      </>}
      <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-gray-700">Open assessment by reference</summary>
        <form onSubmit={event => { event.preventDefault(); void inspect(reference.trim()) }} className="space-y-2">
          <label className="block text-sm text-gray-900">Full assessment reference
            <input required pattern="[a-f0-9]{32}" className="mt-1 block min-h-11 w-full rounded-lg border border-gray-300 p-3" value={reference} onChange={event => setReference(event.target.value)} />
          </label><button className={button}>Open saved assessment</button>
        </form>
      </details>
      {selected && <div ref={result} tabIndex={-1} role="region" className="min-w-0 space-y-4 border-t border-gray-300 pt-4 outline-offset-4 sm:rounded-lg sm:border sm:p-4" aria-label="Saved assessment result">
        <h5 className="text-sm font-semibold text-gray-900">{labels[selected.status]}</h5>
        <details className="text-xs text-gray-600"><summary className="min-h-11 cursor-pointer py-2 text-sm">Assessment details</summary>
          <dl className="space-y-2">
            <div><dt>Saved</dt><dd>{savedTime(selected.prepared_at)}</dd></div>
            {selected.finished_at && <div><dt>Result recorded</dt><dd>{savedTime(selected.finished_at)}</dd></div>}
            <div><dt>Assessment reference</dt><dd className="break-all">{selected.attempt_id}</dd></div>
            <div><dt>{selected.assessment_kind === 'governance_capstone_review_draft' ? 'Saved capstone supervision review' : selected.assessment_kind === 'bounded_batch_review_draft' ? 'Saved batch review' : selected.assessment_kind === 'validation_suite_review_draft' ? 'Saved validation review' : selected.assessment_kind === 'output_workflow_review_draft' ? 'Saved output review' : selected.assessment_kind === 'budget_workflow_review_draft' ? 'Saved budget review' : selected.assessment_kind === 'connected_workflow_review_draft' ? 'Saved run comparison' : selected.assessment_kind === 'workflow_design_review_draft' ? 'Saved workflow approval' : selected.assessment_kind === 'process_design_review_draft' ? 'Saved process reference' : 'Saved run reference'}</dt><dd className="break-all">{selected.governance_review_submission_id || selected.batch_review_submission_id || selected.validation_review_submission_id || selected.output_review_submission_id || selected.budget_review_submission_id || selected.connected_review_submission_id || selected.workflow_design_submission_id || selected.process_submission_id || selected.run_id}</dd></div>
            <div><dt>Course version</dt><dd className="break-all">{selected.course_version}</dd></div>
            {selected.parent_attempt_id && <div><dt>Original assessment reference</dt><dd className="break-all">{selected.parent_attempt_id}</dd></div>}
          </dl>
        </details>
        {selected.parent_attempt_id && <p className="text-sm text-gray-700">This is a technical retry using the original saved evidence.</p>}
        {selected.status === 'grading_unavailable' && <p className="text-sm text-gray-700">A technical problem prevented a final assessment. This is not a failed learner attempt. Your saved work is preserved.</p>}
        {['prepared', 'evaluating'].includes(selected.status) && <p className="text-sm text-gray-700">No final assessment is saved yet. Refresh to check for a result. Reading this page does not start another assessment.</p>}
        {selected.status === 'requirements_supported' && <p className="text-sm text-gray-700">The saved draft checks support these requirements. This result does not complete the module or change earned credit.</p>}
        {selected.status === 'revision_required' && <p className="text-sm text-gray-700">Use the feedback below to check and revise your work. Refreshing this result will keep the original saved assessment.</p>}
        {onOpenWork && <div className="space-y-2 text-sm text-gray-700">
          <button type="button" className={button} disabled={busy || workNavigationDisabled} onClick={() => { focusResult.current = false; onOpenWork(selected) }}>Open saved work to review</button>
          <p>Inspect the saved work, then save any revisions before requesting another assessment. This original feedback and its successful checks remain in history.</p>
        </div>}
        {selected.outcomes.map(outcome => <article key={outcome.outcome_id} className="space-y-2 border-t border-gray-200 pt-3 text-sm text-gray-700">
          <h6 className="font-semibold text-gray-900">{outcome.statement}</h6>
          <p>{outcome.method === 'deterministic' ? 'Execution check' : 'Evidence review'} · {verdicts[outcome.verdict]}</p>
          <p className="whitespace-pre-wrap break-words">{outcome.explanation}</p>
          {outcome.revision_instruction && <p className="whitespace-pre-wrap break-words"><strong>Next step: </strong>{outcome.revision_instruction}</p>}
          {outcome.citations.length > 0 && <details><summary className="min-h-11 cursor-pointer py-2">Evidence cited ({outcome.citations.length})</summary>
            {outcome.citations.map((citation, index) => <blockquote key={index} className="my-2 whitespace-pre-wrap break-words border-l-2 border-gray-300 pl-3">{citation.quote}</blockquote>)}
          </details>}
        </article>)}
      </div>}
    </>}
  </section>
}
