import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { getAutomaticReview, requestAutomaticReview, retryAutomaticReview, requestProcessReview, retryProcessReview, requestWorkflowDesignReview, retryWorkflowDesignReview, requestConnectedReview, retryConnectedReview, requestBudgetReview, retryBudgetReview, requestOutputReview, retryOutputReview, requestValidationReview, retryValidationReview, requestBatchReview, retryBatchReview, requestGovernanceReview, retryGovernanceReview } from '../../api/certification'
import { ApiError } from '../../api/client'
import type { AutomaticReviewStatus, SavedAutomaticReview } from '../../types/certification'

type Request = { request_id: string; parent_attempt_id: string | null }
const labels: Record<AutomaticReviewStatus, string> = { prepared: 'Assessment prepared', evaluating: 'Assessment has no final result yet',
  requirements_supported: 'Draft requirements supported', revision_required: 'Revision needed', grading_unavailable: 'Assessment unavailable' }
const button = 'min-h-11 min-w-0 max-w-full rounded-lg border border-gray-300 bg-white px-2 py-2 text-left text-sm font-medium text-gray-900 [overflow-wrap:anywhere] disabled:opacity-50 sm:px-4'
function stored(key: string): Request | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) || 'null')
    if (value && /^[a-f0-9]{32}$/.test(value.request_id) && (value.parent_attempt_id === null || /^[a-f0-9]{32}$/.test(value.parent_attempt_id))) return value
  } catch { /* Before sending, explain when storage is unavailable. */ }
  return null
}

type AssessmentReferenceName = 'runId' | 'processSubmissionId' | 'workflowDesignSubmissionId' | 'connectedReviewSubmissionId' | 'budgetReviewSubmissionId' | 'outputReviewSubmissionId' | 'validationReviewSubmissionId' | 'batchReviewSubmissionId' | 'governanceReviewSubmissionId'
type AssessmentReference = { [K in AssessmentReferenceName]: { [P in K]: string } & { [P in Exclude<AssessmentReferenceName, K>]?: never } }[AssessmentReferenceName]
export function PracticalAssessment({ enrollmentId, moduleId, runId, processSubmissionId, workflowDesignSubmissionId, connectedReviewSubmissionId, budgetReviewSubmissionId, outputReviewSubmissionId, validationReviewSubmissionId, batchReviewSubmissionId, governanceReviewSubmissionId, onOpenFeedback }: {
  enrollmentId: string; moduleId: string; onOpenFeedback: (attemptId: string) => void
} & AssessmentReference) {
  const governance = moduleId === 'governance' && !!governanceReviewSubmissionId
  const batch = moduleId === 'batch_processing' && !!batchReviewSubmissionId
  const validation = moduleId === 'validation_qa' && !!validationReviewSubmissionId
  const output = moduleId === 'output_delivery' && !!outputReviewSubmissionId
  const budget = moduleId === 'advanced_nodes' && !!budgetReviewSubmissionId
  const connected = moduleId === 'multi_step' && !!connectedReviewSubmissionId && !runId && !processSubmissionId && !workflowDesignSubmissionId
  const workflow = moduleId === 'workflow_design' && !!workflowDesignSubmissionId && !runId && !processSubmissionId
  const process = moduleId === 'process_mapping' && !!processSubmissionId && !runId
  const key = governance ? `certification-governance-assessment:${enrollmentId}:${governanceReviewSubmissionId}` : batch ? `certification-batch-assessment:${enrollmentId}:${batchReviewSubmissionId}` : validation ? `certification-validation-assessment:${enrollmentId}:${validationReviewSubmissionId}` : output ? `certification-output-assessment:${enrollmentId}:${outputReviewSubmissionId}` : budget ? `certification-budget-assessment:${enrollmentId}:${budgetReviewSubmissionId}` : connected ? `certification-connected-assessment:${enrollmentId}:${connectedReviewSubmissionId}` : workflow ? `certification-workflow-assessment:${enrollmentId}:${workflowDesignSubmissionId}` : process ? `certification-process-assessment:${enrollmentId}:${processSubmissionId}` : `certification-assessment:${enrollmentId}:${runId}`
  const [request, setRequest] = useState(() => stored(key))
  const requestRef = useRef(request)
  const [receipt, setReceipt] = useState<SavedAutomaticReview | null>(null)
  const [canFinish, setCanFinish] = useState(false)
  const [busy, setBusy] = useState(false)
  const [activity, setActivity] = useState('')
  const [error, setError] = useState('')
  const sequence = useRef(0), sending = useRef(false), focusResult = useRef(false)
  const resultRef = useRef<HTMLDivElement>(null)
  useEffect(() => () => { sequence.current++ }, [enrollmentId, moduleId, runId, processSubmissionId, workflowDesignSubmissionId, connectedReviewSubmissionId, budgetReviewSubmissionId, outputReviewSubmissionId, validationReviewSubmissionId, batchReviewSubmissionId, governanceReviewSubmissionId])
  useLayoutEffect(() => {
    if (receipt && focusResult.current && resultRef.current) { focusResult.current = false; resultRef.current.focus() }
  }, [receipt])

  function verify(value: SavedAutomaticReview, expected: Request) {
    if (value.attempt_id !== expected.request_id || value.enrollment_id !== enrollmentId || value.module_id !== moduleId || (governance ? !/^[a-f0-9]{32}$/.test(value.run_id || '') || value.governance_review_submission_id !== governanceReviewSubmissionId : batch ? !/^[a-f0-9]{32}$/.test(value.run_id || '') || value.batch_review_submission_id !== batchReviewSubmissionId : validation ? !/^[a-f0-9]{32}$/.test(value.run_id || '') || value.validation_review_submission_id !== validationReviewSubmissionId : output ? !/^[a-f0-9]{32}$/.test(value.run_id || '') || value.output_review_submission_id !== outputReviewSubmissionId : budget ? !/^[a-f0-9]{32}$/.test(value.run_id || '') || value.budget_review_submission_id !== budgetReviewSubmissionId : connected ? !/^[a-f0-9]{32}$/.test(value.run_id || '') || value.connected_review_submission_id !== connectedReviewSubmissionId : workflow ? value.run_id !== null || value.workflow_design_submission_id !== workflowDesignSubmissionId : process ? value.run_id !== null || value.process_submission_id !== processSubmissionId : !runId || value.run_id !== runId)
      || value.parent_attempt_id !== expected.parent_attempt_id || !Object.hasOwn(labels, value.status)
      || value.assessment_kind !== (governance ? 'governance_capstone_review_draft' : batch ? 'bounded_batch_review_draft' : validation ? 'validation_suite_review_draft' : output ? 'output_workflow_review_draft' : budget ? 'budget_workflow_review_draft' : connected ? 'connected_workflow_review_draft' : workflow ? 'workflow_design_review_draft' : process ? 'process_design_review_draft' : 'practical_review_draft') || value.credit_awarded !== false || value.module_completion_eligible !== false
      || value.staff_review_required !== false || value.can_request_review !== false || value.can_retry_review !== false) throw new Error('Assessment identity mismatch')
    return value
  }

  async function act(kind: 'new' | 'retry' | 'check' | 'finish') {
    if (sending.current || (kind === 'finish' && !canFinish)) return
    if ((kind === 'new' && requestRef.current && !receipt) || (kind === 'retry' && receipt?.status !== 'grading_unavailable')) return
    sending.current = true
    const token = ++sequence.current
    setBusy(true); setError(''); setCanFinish(false)
    setActivity(kind === 'check' ? 'Checking the saved assessment…'
      : kind === 'retry' ? 'Requesting a technical retry of the original assessment…'
      : kind === 'finish' ? 'Resuming the original assessment request…' : 'Requesting automatic assessment…')
    let sent = false
    try {
      const next = kind === 'new' || kind === 'retry'
        ? { request_id: crypto.randomUUID().replaceAll('-', ''), parent_attempt_id: kind === 'retry' ? receipt!.attempt_id : null }
        : requestRef.current
      if (!next) throw new Error('No assessment reference')
      if (kind !== 'check') {
        sessionStorage.setItem(key, JSON.stringify(next)); requestRef.current = next; setRequest(next)
      }
      let value: SavedAutomaticReview
      if (kind === 'check') value = verify(await getAutomaticReview(enrollmentId, next.request_id), next)
      else {
        sent = true
        value = verify(await (next.parent_attempt_id
          ? (governance ? retryGovernanceReview : batch ? retryBatchReview : validation ? retryValidationReview : output ? retryOutputReview : budget ? retryBudgetReview : connected ? retryConnectedReview : workflow ? retryWorkflowDesignReview : process ? retryProcessReview : retryAutomaticReview)(enrollmentId, next.parent_attempt_id, next.request_id)
          : governance ? requestGovernanceReview(enrollmentId, governanceReviewSubmissionId!, next.request_id) : batch ? requestBatchReview(enrollmentId, batchReviewSubmissionId!, next.request_id) : validation ? requestValidationReview(enrollmentId, validationReviewSubmissionId!, next.request_id) : output ? requestOutputReview(enrollmentId, outputReviewSubmissionId!, next.request_id) : budget ? requestBudgetReview(enrollmentId, budgetReviewSubmissionId!, next.request_id) : connected ? requestConnectedReview(enrollmentId, connectedReviewSubmissionId!, next.request_id) : workflow ? requestWorkflowDesignReview(enrollmentId, workflowDesignSubmissionId!, next.request_id) : process ? requestProcessReview(enrollmentId, processSubmissionId!, next.request_id) : requestAutomaticReview(enrollmentId, runId!, next.request_id)), next)
      }
      if (token !== sequence.current) return
      focusResult.current = true; setReceipt(value)
      setCanFinish(value.status === 'prepared' || value.status === 'evaluating')
    } catch (failure) {
      if (token !== sequence.current) return
      setReceipt(null)
      if (sent && failure instanceof ApiError && failure.status === 409
        && failure.code === 'CERTIFICATION_REVIEW_EXISTS' && /^[a-f0-9]{32}$/.test(failure.existingReviewId || '')) {
        const original = { request_id: failure.existingReviewId!, parent_attempt_id: requestRef.current?.parent_attempt_id ?? null }
        // This server-confirmed reference still needs the normal owned receipt
        // verification. Do not dispatch or finish it as part of conflict recovery.
        requestRef.current = original; setRequest(original)
        try {
          sessionStorage.setItem(key, JSON.stringify(original))
          setError('This saved work already has an assessment request. Check its original saved assessment; no additional assessment was started.')
        } catch {
          setError('This saved work already has an assessment request. Check it here. This browser could not preserve its reference for reopening.')
        }
      } else if (kind === 'check' && failure instanceof ApiError && failure.status === 404) {
        setCanFinish(true)
        setError('No assessment is saved for this reference yet. Save your required decisions, then finish this same request.')
      } else if (kind !== 'check' && !sent) setError('This browser could not preserve the request. Allow session storage before assessing; no assessment request was sent.')
      else setError(`${failure instanceof ApiError && [409, 422].includes(failure.status) ? failure.message + '. ' : ''}We could not confirm the assessment. Check its saved state before taking another action. Checking does not run a model.`)
    } finally { sending.current = false; if (token === sequence.current) setBusy(false) }
  }

  const final = receipt && ['requirements_supported', 'revision_required', 'grading_unavailable'].includes(receipt.status)
  return <section className="min-w-0 space-y-3 border-t border-gray-200 pt-4 [overflow-wrap:anywhere]" aria-label="Request automatic assessment">
    <h5 className="text-base font-semibold text-gray-900">Assess your saved work</h5>
    <p className="text-sm text-gray-700">{governance ? 'Automatic assessment reviews your recorded scope correction, source finding, actual original and repaired results, accountable memo and exact private handoff receipts. Your explanations are assessed against that saved work. It does not repeat extraction or delivery.' : batch ? 'Automatic assessment checks the original document inventory and reviews the actual pilot, targeted retries and your saved decisions. Source checks can require revision despite a favorable model response. It never reruns extraction.' : validation ? 'Automatic assessment reviews your original expectations, source references, actual failure, repaired revision, full retest and saved explanation. Source checks can require revision even when a model approves. It does not rerun extraction.' : output ? 'Automatic assessment reviews the actual file contents, your exact release choice, private handoff receipts and saved interpretation. It does not regenerate files or repeat a handoff.' : budget ? 'Automatic assessment reviews your saved calculations, actual task inputs/results and method and dependency explanations. A model verdict cannot override incorrect arithmetic. It does not rerun the workflow.' : connected ? 'Automatic assessment reviews both original executions, their saved stage results and your comparison answers. It does not rerun either workflow.' : workflow ? 'Automatic assessment uses the system judge to review the approved workflow configuration and your saved decisions. It does not run the workflow or release anything.' : process ? 'Automatic assessment uses the system judge to review this saved process map, rationale and task brief against its original case. It does not execute a workflow.' : 'Save your source checks first. Automatic assessment uses the system judge to review the saved run, its scope approval and your latest saved value checks.'} It may incur model usage. Draft feedback does not award credit or certification.</p>
    {!request && <button type="button" className={button} disabled={busy} onClick={() => { void act('new') }}>Assess saved work automatically</button>}
    {request && <>
      <button type="button" className={button} disabled={busy} onClick={() => { void act('check') }}>Check saved assessment</button>
      {!receipt && <p className="text-sm text-gray-700">Your original request is preserved in this tab. Check it before starting another assessment.</p>}
      {canFinish && <>
        <p className="text-sm text-gray-700">Finish the original request using its saved evidence if available. This can start a prepared assessment or recover a stalled one. An assessment already running is not dispatched again.</p>
        <button type="button" className={button} disabled={busy} onClick={() => { void act('finish') }}>Finish requested assessment</button>
      </>}
    </>}
    {busy && <p role="status" className="text-sm text-gray-700">{activity}</p>}
    {busy && <p className="text-sm text-gray-700">Closing this panel does not confirm whether a sent assessment finished or stopped. Reopen the same saved work and check its assessment before retrying.</p>}
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    {receipt && <div ref={resultRef} tabIndex={-1} role="region" aria-label="Requested assessment status" className="min-w-0 space-y-3 outline-offset-4">
      <h6 className="text-sm font-semibold text-gray-900">{labels[receipt.status]}</h6>
      {receipt.status === 'grading_unavailable' && <p className="text-sm text-gray-700">A technical problem prevented a final assessment. This is not a failed learner attempt. A technical retry uses the original saved evidence.</p>}
      {receipt.status === 'revision_required' && <p className="text-sm text-gray-700">Open the saved feedback, revise your work and save your decisions before requesting a new assessment.</p>}
      {receipt.status === 'requirements_supported' && <p className="text-sm text-gray-700">The draft assessment supports the saved requirements. It does not complete the module or change earned credit.</p>}
      <button type="button" className={button} disabled={busy} onClick={() => { focusResult.current = false; onOpenFeedback(receipt.attempt_id) }}>Open saved feedback</button>
      {receipt.status === 'grading_unavailable' && <button type="button" className={button} disabled={busy} onClick={() => { void act('retry') }}>Retry the original assessment</button>}
      {final && !process && !workflow && !connected && !budget && !output && !validation && !batch && !governance && <button type="button" className={button} disabled={busy} onClick={() => { void act('new') }}>Assess revised saved work</button>}
      <details className="text-sm text-gray-700"><summary className="min-h-11 cursor-pointer py-2">Assessment reference</summary><p className="break-all">{receipt.attempt_id}</p>
        {receipt.parent_attempt_id && <p className="break-all">Original assessment: {receipt.parent_attempt_id}</p>}
      </details>
    </div>}
  </section>
}
