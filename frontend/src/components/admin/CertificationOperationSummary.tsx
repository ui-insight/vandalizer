import type { CertificationSupportOperations } from '../../api/admin'
const reviewLabels: Record<string, string> = {
  prepared: 'Review saved; not started', evaluating: 'Automatic review pending', requirements_supported: 'Assessed requirements supported',
  revision_required: 'Evidence needs revision', grading_unavailable: 'Automatic grading unavailable', unavailable: 'Record needs reconciliation',
}
const runLabels: Record<string, string> = {
  prepared: 'Run plan saved', executing: 'Run awaiting a final receipt', completed: 'Execution recorded',
  failed: 'Run ended without completion', uncertain: 'Run outcome uncertain', unavailable: 'Record needs reconciliation',
}
const handoffLabels: Record<string, string> = { failed: 'Training handoff stopped before delivery', delivered: 'Private training copy saved', unavailable: 'Record needs reconciliation' }
const groupLabels = { automatic_review: 'Automatic reviews', lab_run: 'Lab runs', private_handoff: 'Private training handoffs' }
const referenceLabels: Record<string, string> = {
  review_id: 'Original file review', release_id: 'Original release approval', previous_failed_id: 'Original failed handoff',
  run_id: 'Original run', parent_attempt_id: 'Original automatic review', input_snapshot_id: 'Saved inputs',
  process_submission_id: 'Process submission', workflow_design_submission_id: 'Workflow design submission',
  connected_review_submission_id: 'Connected workflow review', budget_review_submission_id: 'Budget review',
  output_review_submission_id: 'Output review', validation_review_submission_id: 'Validation review',
  batch_review_submission_id: 'Batch review', governance_review_submission_id: 'Governance review',
}
export function CertificationOperationSummary({ operations }: { operations: CertificationSupportOperations }) {
  return <div className="space-y-3 border-t border-gray-200 pt-3">
    <h4 className="font-semibold">Automatic assessments, runs and handoffs</h4>
    <p className="text-gray-700">Automatic reviews and runs show up to five outstanding and five recently saved records, with duplicates removed. Private handoffs show the five latest terminal receipts. Saved results do not select evidence or award module credit.</p>
    {operations.worker_marked_in_flight && <p>A course operation is still marked in flight. Inspect its original request before starting duplicate work.</p>}
    {operations.course_change_pending && <p>A course selection change is pending. The learner should check that original request before switching courses again.</p>}
    {operations.groups.map(group => <div key={group.kind} className="space-y-3">
      <h5 className="font-semibold">{groupLabels[group.kind]}</h5>
      {group.records.length === 0 && <p>No saved {group.kind === 'automatic_review' ? 'automatic review' : group.kind === 'lab_run' ? 'lab run' : 'private training handoff'} records exist for this enrollment.</p>}
      {group.records.map((entry, index) => <article key={entry.request_id ?? `unavailable-${index}`} className="space-y-2 rounded border border-gray-300 p-3">
        <p className="font-medium">{entry.module_title ? `${entry.module_title} · ` : ''}{(group.kind === 'automatic_review' ? reviewLabels : group.kind === 'lab_run' ? runLabels : handoffLabels)[entry.state] || 'Record needs reconciliation'}</p>
        <p>{entry.next_step}</p>
        {!!entry.failed_required_outcomes?.length && <div><p className="font-medium">Outcomes requiring revision in this review</p><ul className="mt-1 list-disc space-y-1 pl-5">{entry.failed_required_outcomes.map(outcome => <li key={outcome.outcome_id}>{outcome.statement}</li>)}</ul></div>}
        {entry.request_id && <details><summary style={{ minHeight: 44 }} className="cursor-pointer py-3 font-medium">Saved operation references</summary><dl className="space-y-2 text-xs text-gray-700">
          <div><dt>{group.kind === 'automatic_review' ? 'Automatic review' : group.kind === 'lab_run' ? 'Lab run' : 'Private training handoff'}</dt><dd>{entry.request_id}</dd></div>
          {Object.entries(entry.references ?? {}).filter(([key]) => referenceLabels[key]).map(([key, value]) => <div key={key}><dt>{referenceLabels[key]}</dt><dd>{value}</dd></div>)}
        </dl></details>}
      </article>)}
      {group.more_pending && <p>Additional outstanding records exist beyond these five. This is not a complete pending-work inventory.</p>}
      {group.more_recent && <p>Older saved records also exist. The learner can open the original course for its history.</p>}
    </div>)}
    <p className="text-gray-700">Provider diagnostics and learner source text are excluded. Feedback and technical retry controls remain in the learner’s course; this view does not create a staff grading task.</p>
  </div>
}
