import { useCallback, useEffect, useRef, useState } from 'react'
import { getCertificationRecovery, recoverCertificationCompletion, type CertificationProgressItem, type CertificationRecoveryAction, type CertificationRecoveryReceipt, type CertificationRecoverySnapshot } from '../../api/admin'
import { useAdminQuery } from './shared/useAdminQuery'

const RESULT_COPY: Record<CertificationRecoveryReceipt['status'], string> = {
  review_changed: 'The reviewed worker changed or finished before recovery. No recovery was applied; inspect the current status.',
  no_assessment_started: 'The interrupted worker was released before assessment started. The learner can submit again.',
  saved_result: 'The original result is preserved. The learner can check the saved result in their course.',
  retry_saved_grade: 'The saved grade is preserved. The learner can check the saved result to finish completion.',
  interrupted_before_grade: 'The interrupted evaluation ended without an award. The learner can submit a new assessment.',
}
const buttonClass = 'rounded border border-gray-400 bg-white px-3 py-2 text-sm font-medium text-gray-900 disabled:opacity-50'

export function CertificationRecoveryReview({ item, onClose }: { item: CertificationProgressItem; onClose: () => void }) {
  const request = useCallback(() => getCertificationRecovery(item.user_id, item.enrollment_id!), [item.user_id, item.enrollment_id])
  const { data, loading, error, load: refresh } = useAdminQuery(request)
  const [reason, setReason] = useState('')
  const [acknowledged, setAcknowledged] = useState(false)
  const [pending, setPending] = useState<{ action: CertificationRecoveryAction; review: CertificationRecoverySnapshot } | null>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [receipt, setReceipt] = useState<CertificationRecoveryReceipt | null>(null)
  const submitting = useRef(false)
  const region = useRef<HTMLElement>(null)
  useEffect(() => { region.current?.focus() }, [])

  const apply = async () => {
    if (submitting.current || !data?.can_apply || (!pending && (!acknowledged || !data.review.can_recover || reason.trim().length < 5))) return
    const reviewed = pending ?? { action: { request_id: crypto.randomUUID().replaceAll('-', ''), review_sha256: data.review.review_sha256, reason: reason.trim() }, review: data.review }
    setPending(reviewed)
    setFailure(null)
    setReceipt(null)
    setBusy(true)
    submitting.current = true
    try {
      const result = await recoverCertificationCompletion(item.user_id, item.enrollment_id!, reviewed.action)
      setReceipt(result)
      setPending(null)
      setAcknowledged(false)
      setReason('')
      await refresh()
    } catch (error) {
      setFailure(error instanceof Error ? error.message : 'Recovery could not be confirmed. Retry the same reviewed action.')
    } finally { submitting.current = false; setBusy(false) }
  }

  const review = pending?.review ?? data?.review
  return (
    <section ref={region} tabIndex={-1} aria-labelledby="certification-recovery-heading" className="space-y-4 rounded-lg border border-gray-300 bg-white p-4 text-sm text-gray-900">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h3 id="certification-recovery-heading" className="font-semibold">Completion recovery: {item.name || item.email || item.user_id}</h3><p className="mt-1 text-gray-700">{item.course_title}</p></div>
        <button type="button" className={buttonClass} disabled={busy} onClick={onClose}>Close review</button>
      </div>
      {loading && <p role="status">Loading recovery review…</p>}
      {error && <p role="alert">{error}</p>}
      {review && <>
        <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div><dt className="font-medium">Course version</dt><dd className="break-all">{review.course_version}</dd></div>
          <div><dt className="font-medium">Module</dt><dd>{review.module_title || 'No assessment started'}</dd></div>
          <div><dt className="font-medium">Completion state</dt><dd>{review.in_flight ? 'Worker still marked in flight' : review.attempt_state || 'No pending assessment'}</dd></div>
          <div><dt className="font-medium">Earned progress</dt><dd>{review.total_xp} XP{review.certified ? ' · certified' : ''}</dd></div>
        </dl>
        <p>{review.explanation}</p>
        <p className="text-gray-700">This action preserves earned credit and credentials. It does not rerun grading, change courses, provision documents or retry external jobs.</p>
        <details><summary className="cursor-pointer font-medium">Reviewed record identities</summary><dl className="mt-2 space-y-2 break-all text-xs"><div><dt>Enrollment</dt><dd>{review.enrollment_id}</dd></div><div><dt>Attempt</dt><dd>{review.attempt_id || 'Not started'}</dd></div><div><dt>Write</dt><dd>{review.write_id || 'Released'}</dd></div><div><dt>Review</dt><dd>{review.review_sha256}</dd></div></dl></details>
      </>}
      {data?.can_apply && (review?.can_recover || pending) && <div className="space-y-3 border-t border-gray-200 pt-3">
        <label className="block font-medium">Reason for recovery<textarea value={pending?.action.reason ?? reason} onChange={event => setReason(event.target.value)} disabled={busy || !!pending} maxLength={1000} rows={3} className="mt-1 block w-full rounded border border-gray-400 bg-white p-2 font-normal" /></label>
        {!pending && <label className="flex items-start gap-2"><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} className="mt-1" />I reviewed this learner, course and submission. Revoke the completion worker if still active and reconcile its saved result.</label>}
        {pending && <p>The original review and reason are retained for this request. Retrying checks the same recovery.</p>}
        <button type="button" className={buttonClass} disabled={busy || loading || (!pending && (!acknowledged || reason.trim().length < 5))} onClick={apply}>{busy ? 'Recovering…' : pending ? 'Retry this recovery' : 'Apply reviewed recovery'}</button>
      </div>}
      {data && !data.can_apply && <p>Staff can inspect this state. A full administrator must apply recovery.</p>}
      {failure && <div className="space-y-2"><p role="alert" className="text-red-800">{failure}</p>{pending && <button type="button" className={buttonClass} disabled={busy} onClick={() => { setPending(null); setAcknowledged(false); setFailure(null); refresh() }}>Review current state and recovery history</button>}</div>}
      {receipt && <p role="status" className="text-green-800">{RESULT_COPY[receipt.status]}</p>}
      <button type="button" className={buttonClass} disabled={busy || loading} onClick={() => { setFailure(null); refresh() }}>Refresh recovery status</button>
      {data && data.history.length > 0 && <div className="space-y-3 border-t border-gray-200 pt-3"><h4 className="font-semibold">Recent recovery history · latest 10</h4>
        {data.history.map(entry => <article key={entry.request_id} className="space-y-1 rounded border border-gray-200 p-3">
          <p className="font-medium">{entry.state === 'completed' ? 'Completed recovery' : 'Recovery awaiting a confirmed result'}</p>
          <p className="break-words">{entry.reason}</p><p className="text-xs text-gray-700">{new Date(entry.created_at).toLocaleString()}</p><p className="break-all text-xs text-gray-700">Operator: {entry.actor_user_id} · Request: {entry.request_id}</p>
          {entry.result && <p>{RESULT_COPY[entry.result.status]}</p>}
          {data.can_apply && entry.can_resume && !pending && <button type="button" className={buttonClass} disabled={busy} onClick={() => { setPending({ action: { request_id: entry.request_id, review_sha256: entry.review_sha256, reason: entry.reason }, review: { ...entry.review, review_sha256: entry.review_sha256 } }); setReceipt(null); setFailure(null) }}>Resume reviewed recovery</button>}
        </article>)}
      </div>}
    </section>
  )
}
