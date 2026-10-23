import type { CertificationSupportSummary } from '../../api/admin'

export function CertificationAccessHistory({ history }: { history: CertificationSupportSummary['access_changes'] }) {
  return <div className="space-y-3 border-t border-gray-200 pt-3">
    <h4 className="font-semibold">Administrator access changes</h4>
    <p>Access changes do not establish assessed credit, award XP or issue a certificate.</p>
    {!history || history.state === 'unavailable' ? <p>Access-change history is unavailable. No reason or authorizing administrator is inferred.</p>
      : history.state === 'not_recorded' ? <p>{history.historical_unlocked ? 'The course record does not identify the reason or authorizing administrator for this historical unlock.' : 'No administrator access changes are recorded for this course.'}</p>
      : history.changes.map(change => <article key={change.request_id} className="space-y-2 rounded border border-gray-300 p-3">
        <h5 className="font-medium">Prerequisite access {change.unlocked ? 'unlocked' : 're-locked'}</h5>
        <dl className="space-y-1"><div><dt className="font-medium">Authorizing administrator</dt><dd>{change.actor_user_id}</dd></div>
          <div><dt className="font-medium">Recorded time</dt><dd>{change.recorded_at}</dd></div>
          <div><dt className="font-medium">Reason</dt><dd className="whitespace-pre-wrap">{change.reason}</dd></div></dl>
      </article>)}
    {history?.older_available && <p>Showing the latest 10 access changes. Earlier changes remain in the support record.</p>}
  </div>
}
