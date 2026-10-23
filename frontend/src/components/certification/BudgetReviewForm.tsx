import type { Ref } from 'react'
import type { BudgetRequest, BudgetReviewBody, BudgetRun } from '../../types/budgetWorkflow'
import { draftStrings, useCourseDraft } from '../../hooks/useCourseDraft'
import { CourseDraftNotice } from './CourseDraftNotice'
import { BudgetRunEvidence } from './BudgetWorkflowEvidence'
import { connectedButton as button, connectedControl as control } from './ConnectedWorkflowEvidence'

export function BudgetReviewForm({ run, previous, initialAnswers, locked, send, formRef }: {
  run: BudgetRun; previous: string | null; initialAnswers: BudgetReviewBody['answers']; locked: boolean; send: (request: BudgetRequest) => void; formRef?: Ref<HTMLFormElement>
}) {
  const [answers, setAnswers, status] = useCourseDraft(
    ['budget-review', run.enrollment_id, run.manifest_sha256, run.run_id, run.result_sha256, run.case_sha256, previous],
    initialAnswers, draftStrings(['calculation_review', 'dependency_review'], 8000))
  return <form ref={formRef} tabIndex={-1} aria-label="Review budget results" className="min-w-0 space-y-3 rounded-lg border border-gray-300 p-3" onSubmit={event => { event.preventDefault(); send({ action: 'review', body: {
    request_id: crypto.randomUUID().replaceAll('-', ''), run_id: run.run_id, result_sha256: run.result_sha256!, case_sha256: run.case_sha256, answers, previous_submission_id: previous, consent: 'save_budget_calculation_and_dependency_review' } }) }}>
    <h5 className="text-base font-semibold">3. Explain the actual results</h5><p className="text-sm">Reviewing run {run.run_id.slice(0, 8)}. {previous ? 'This creates a linked revision and keeps your original answers.' : 'Your method decision and calculations stay bound to this run.'}</p>
    <details><summary className="min-h-11 cursor-pointer py-2 text-sm">Read selected run evidence</summary><BudgetRunEvidence run={run} /></details>
    {run.input_snapshot.case.questions.filter(question => question.phase === 'after_execution').map(question => <label key={question.id} className="block text-sm">{question.prompt}<textarea className={`${control} min-h-36`} rows={6} required maxLength={8000} disabled={locked} value={answers[question.id as keyof typeof answers]} onChange={event => setAnswers(value => ({ ...value, [question.id]: event.target.value }))} /></label>)}
    <CourseDraftNotice status={status} />
    <button className={button} disabled={locked}>Save calculation and dependency review</button>
  </form>
}
