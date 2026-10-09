import { useEffect, useRef, useState } from 'react'
import type { CertificationAccessRequest, CertificationProgressItem } from '../../api/admin'

export function CertificationAccessChange({ item, onApply, onClose }: {
  item: CertificationProgressItem
  onApply: (request: CertificationAccessRequest) => Promise<void>
  onClose: (needsRefresh: boolean) => void
}) {
  const [reason, setReason] = useState('')
  const [pending, setPending] = useState<CertificationAccessRequest | null>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const sending = useRef(false)
  const region = useRef<HTMLElement>(null)
  useEffect(() => { region.current?.focus() }, [])
  const apply = async () => {
    if (sending.current || (!pending && reason.trim().length < 5)) return
    const request = pending ?? { request_id: crypto.randomUUID().replaceAll('-', ''), unlocked: !item.unlocked, reason: reason.trim() }
    setPending(request)
    sending.current = true
    setBusy(true)
    setFailure(null)
    try { await onApply(request) }
    catch (error) { setFailure(error instanceof Error ? error.message : 'The access change could not be confirmed.') }
    finally { sending.current = false; setBusy(false) }
  }
  const buttonClass = 'rounded border border-gray-400 bg-white px-3 py-2 text-sm font-medium text-gray-900 disabled:opacity-50'
  return <section ref={region} tabIndex={-1} aria-labelledby="certification-access-heading" className="space-y-4 rounded-lg border border-gray-300 bg-white p-4 text-sm text-gray-900 [overflow-wrap:anywhere]">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 w-full sm:w-auto sm:flex-1"><h3 id="certification-access-heading" className="font-semibold">Change module access: {item.name || item.email || item.user_id}</h3><p>{item.course_title || 'Historical course'} · {item.course_version || 'Version not recorded'}</p></div>
      <button type="button" style={{ minHeight: 44 }} className={buttonClass} disabled={busy} onClick={() => onClose(!!pending)}>Close access change</button>
    </div>
    <p>{item.unlocked ? 'Re-lock prerequisite access' : 'Unlock prerequisite access'} for this course. This changes access only; it does not complete assessments, award XP or issue a certificate.</p>
    <label className="block space-y-2"><span className="font-medium">Reason for access change</span><textarea rows={3} maxLength={1000} value={reason} disabled={busy || !!pending} onChange={event => setReason(event.target.value)} className="block w-full rounded border border-gray-400 p-2" /></label>
    <p>Your administrator identity and reason will be saved in the support history with this change.</p>
    {failure && <div role="alert" className="space-y-2"><p>{failure}</p><p>Retry the same request, or close and refresh the saved status before making another change.</p></div>}
    <button type="button" style={{ minHeight: 44 }} className={buttonClass} disabled={busy || (!pending && reason.trim().length < 5)} onClick={apply}>{busy ? 'Saving access change…' : pending ? 'Retry same access change' : 'Save access change'}</button>
  </section>
}
