import type { Ref } from 'react'
import { useCourseDraft, draftStrings } from '../../hooks/useCourseDraft'
import type { ConnectedList, ConnectedRun, ConnectedRequest } from '../../types/connectedWorkflow'
import { connectedButton as button, connectedControl as control } from './ConnectedWorkflowEvidence'
import { CourseDraftNotice } from './CourseDraftNotice'
export const connectedAnswerLabels = { connection_repair: 'Compare the connection repair', source_review: 'Check facts and interpretation' }
type Answers = Record<keyof typeof connectedAnswerLabels, string>
export function ConnectedComparisonForm({ listing, original, corrected, previous, initialAnswers, locked, send, formRef }: {
  listing: ConnectedList; original: ConnectedRun | null; corrected: ConnectedRun | null; previous: string | null; initialAnswers: Answers;
  locked: boolean; send: (request: ConnectedRequest) => void; formRef?: Ref<HTMLFormElement>;
}) {
  const [answers, setAnswers, status] = useCourseDraft(['connected-comparison', listing.enrollment_id, listing.manifest_sha256, listing.case.case_sha256,
    original?.run_id || null, original?.result_sha256 || null, corrected?.run_id || null, corrected?.result_sha256 || null, previous],
  initialAnswers, draftStrings(['connection_repair', 'source_review'], 8000))
  const selected = !!original && !!corrected && original.run_id !== corrected.run_id
  return <form ref={formRef} tabIndex={-1} aria-label="Compare actual connected runs" className="min-w-0 space-y-4 border-t border-gray-200 pt-4 outline-offset-4" onSubmit={event => { event.preventDefault(); if (!locked && selected && original && corrected) send({ action: 'review', body: { request_id: crypto.randomUUID().replaceAll('-', ''), original_run_id: original.run_id, original_result_sha256: original.result_sha256!, corrected_run_id: corrected.run_id, corrected_result_sha256: corrected.result_sha256!, case_sha256: listing.case.case_sha256, answers, previous_submission_id: previous, consent: 'save_connected_workflow_result_review' } }) }}>
      <h5 className="text-base font-semibold text-gray-900">2. Compare your actual runs</h5>
      <p className="text-sm text-gray-700">Open each completed run above and select its role. Use two revisions of the same workflow on the same assigned source. The authored example cannot replace an actual run.</p>
      <p className="text-sm text-gray-900">Original: {original ? original.run_id.slice(0, 8) : 'Not selected'} · Corrected: {corrected ? corrected.run_id.slice(0, 8) : 'Not selected'}</p>
      {original?.run_id === corrected?.run_id && original && <p role="alert" className="text-sm text-red-800">Choose two different completed runs.</p>}
      {previous && <p className="text-sm text-gray-700">This saves a linked revision. Your original comparison remains available.</p>}
      {listing.case.questions.filter(item => item.phase === 'after_execution').map(question => <label key={question.id} className="block space-y-2 text-sm text-gray-900"><span className="font-semibold">{connectedAnswerLabels[question.id as keyof typeof connectedAnswerLabels]}</span><span className="block text-gray-700">{question.prompt}</span><textarea className={`${control} min-h-36`} rows={6} required maxLength={8000} disabled={locked || !selected} value={answers[question.id as keyof typeof answers]} onChange={event => setAnswers(current => ({ ...current, [question.id]: event.target.value }))} /></label>)}
      <CourseDraftNotice status={status} /><button className={button} disabled={locked || !original || !corrected || original.run_id === corrected.run_id}>Save comparison and source review</button>
    </form>
}
