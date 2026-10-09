import { useCallback, useEffect, useRef } from 'react'
import { getCertificationProgressDetail, type CertificationProgressItem } from '../../api/admin'
import { useAdminQuery } from './shared/useAdminQuery'
import { CertificationOperationSummary } from './CertificationOperationSummary'
import { CertificationAccessHistory } from './CertificationAccessHistory'

const buttonClass = 'rounded border border-gray-400 bg-white px-3 py-2 text-sm font-medium text-gray-900 disabled:opacity-50'
const stateLabels: Record<string, string> = {
  evaluating: 'Completion awaiting a result', graded: 'Grade saved; completion pending', applied: 'Credit recorded',
  rejected: 'Required checks not met', failed: 'Technical completion failure', unavailable: 'Record needs reconciliation',
}

export function CertificationLearnerSummary({ item, onClose }: { item: CertificationProgressItem; onClose: () => void }) {
  const request = useCallback(() => getCertificationProgressDetail(item.user_id, item.enrollment_id ?? undefined), [item.user_id, item.enrollment_id])
  const { data, loading, error, load: refresh } = useAdminQuery(request)
  const region = useRef<HTMLElement>(null)
  useEffect(() => { region.current?.focus() }, [])
  // A result must identify the exact row that was opened, including legacy rows.
  const matches = data && data.user_id === item.user_id && (data.enrollment_id ?? null) === (item.enrollment_id ?? null)
    && (!item.progress_id || data.progress_id === item.progress_id) && (data.course_version ?? null) === (item.course_version ?? null)
  const summary = matches ? data.support_summary : null
  return <section ref={region} tabIndex={-1} aria-labelledby="certification-status-heading" className="space-y-4 rounded-lg border border-gray-300 bg-white p-4 text-sm text-gray-900 [overflow-wrap:anywhere]">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 flex-1"><h3 id="certification-status-heading" className="font-semibold">Learning status: {item.name || item.email || item.user_id}</h3><p className="mt-1">{item.course_title || 'Historical course'}</p><p className="mt-1 text-gray-700">Read-only support snapshot</p></div>
      <button type="button" style={{ minHeight: 44 }} className={buttonClass} onClick={onClose}>Close status</button>
    </div>
    {loading && <p role="status">Loading saved learning status…</p>}
    {error && <p role="alert">{error}</p>}
    {data && !matches && <p role="alert">The course record changed. Close this view and refresh the enrollment list before continuing.</p>}
    {matches && !summary && <p>Saved learning details are unavailable. No assessment or reading position is inferred.</p>}
    {matches && summary && <>
      <p>{summary.explanation}</p>
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div><dt className="font-medium">Course version</dt><dd>{data.course_version || 'Historical version unknown'}</dd></div>
        <div><dt className="font-medium">Course selection</dt><dd>{data.is_active == null ? 'Not recorded' : data.is_active ? 'Selected course' : 'Preserved course history'}</dd></div>
        <div><dt className="font-medium">Recorded progress</dt><dd>{data.modules_completed}/{data.modules_total} modules · {data.total_xp} XP</dd></div>
        <div><dt className="font-medium">Completion</dt><dd>{data.certified ? 'Recorded as certified' : 'Not recorded as certified'}</dd></div>
      </dl>
      <CertificationAccessHistory history={summary.access_changes} />
      <div className="space-y-1 border-t border-gray-200 pt-3"><h4 className="font-semibold">Last saved reading position</h4>
        {summary.position_status === 'saved' && summary.last_saved_lesson ? <><p>{summary.last_saved_lesson.module_title} · {summary.last_saved_lesson.lesson_title}</p><p className="text-gray-700">Lesson revision {summary.last_saved_lesson.revision}. Reading position does not establish assessment credit.</p></>
          : <p>{summary.position_status === 'unavailable' ? 'The stored position could not be matched to the original lesson. No location is inferred.' : 'No server reading position is recorded. The learner may have a browser-only position.'}</p>}
      </div>
      <div className="space-y-2 border-t border-gray-200 pt-3"><h4 className="font-semibold">Unfinished completion requests</h4>
        {summary.pending_credential && <p>A credential issuance record is pending. Inspect the original completion recovery before issuing anything again.</p>}
        {summary.pending_completions.length === 0 ? <p>No unfinished module completion request is recorded.</p> : summary.pending_completions.map(entry => <article key={entry.attempt_id} className="space-y-1 rounded border border-gray-300 p-3">
          <h5 className="font-medium">{entry.module_title}</h5><p>{entry.in_flight ? 'A worker is still marked in flight. ' : ''}{entry.next_step}</p>
        </article>)}
        <p className="text-gray-700">This list covers module completion requests. It does not imply that every lab job or automatic assessment has finished. Assessment feedback remains in the learner’s course; routine grading is automatic.</p>
      </div>
      <div className="space-y-3 border-t border-gray-200 pt-3"><h4 className="font-semibold">Recent module completion history · latest 10</h4>
        {summary.recent_completions.length === 0 && <p>No module completion requests are recorded for this course.</p>}
        {summary.recent_completions.map((entry, index) => <article key={entry.attempt_id ?? `unavailable-${index}`} className="space-y-2 rounded border border-gray-300 p-3">
          <h5 className="font-medium">{entry.module_title ? `${entry.module_title} · ` : ''}{stateLabels[entry.state] || 'Record needs reconciliation'}</h5>
          <p>{entry.next_step}</p>
          {!!entry.failed_required_outcomes?.length && <div><p className="font-medium">Required outcomes not met in this request</p><ul className="mt-1 list-disc space-y-1 pl-5">{entry.failed_required_outcomes.map(outcome => <li key={outcome.outcome_id}>{outcome.statement}</li>)}</ul></div>}
          {entry.attempt_id && <details><summary style={{ minHeight: 44 }} className="cursor-pointer py-3 font-medium">Original request references</summary><dl className="space-y-2 text-xs text-gray-700">
            <div><dt>Completion request</dt><dd>{entry.attempt_id}</dd></div>
            {entry.created_at && <div><dt>Recorded time (as stored)</dt><dd>{entry.created_at}</dd></div>}
            {entry.selected_evidence?.review_attempt_id && <div><dt>Selected automatic review</dt><dd>{entry.selected_evidence.review_attempt_id}</dd></div>}
            {entry.selected_evidence?.scenario_attempt_id && <div><dt>Selected scenario assessment</dt><dd>{entry.selected_evidence.scenario_attempt_id}</dd></div>}
          </dl></details>}
        </article>)}
        {summary.older_completions_available && <p>Older completion requests exist; this snapshot shows only the latest 10.</p>}
      </div>
      {summary.operations && <CertificationOperationSummary operations={summary.operations} />}
      <p className="text-xs text-gray-700">Snapshot observed: {summary.observed_at}. Refresh before relying on its status.</p>
    </>}
    <button type="button" style={{ minHeight: 44 }} className={buttonClass} disabled={loading} onClick={refresh}>Refresh learning status</button>
  </section>
}
