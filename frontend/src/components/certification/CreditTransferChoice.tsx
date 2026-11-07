import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { applyCreditTransfer, getCreditTransfer, previewCreditTransfer } from '../../api/creditTransfer'
import type { CreditTransferPreview, CreditTransferRequest, TransferModule } from '../../api/creditTransfer'
import type { CompletionResult } from '../../types/certification'
import { choiceButton } from './ExplicitCourseSwitch'
import { choiceDigest, choiceId } from '../../api/courseChoices'

type Pending = { request: CreditTransferRequest; manifest: string; title: string; xp: number }
const consentText = 'transfer_reviewed_module_credit_preserve_original_no_new_xp_reward'
function validRequest(request: CreditTransferRequest, enrollment: string) {
  return request && choiceId(request.request_id) && choiceId(request.source_enrollment_id)
    && request.target_enrollment_id === enrollment && choiceDigest(request.preview_sha256)
    && /^[a-z][a-z0-9_]*$/.test(request.module_id) && request.consent === consentText
}

export function CreditTransferChoice({ enrollmentId, onRefreshCourse }: { enrollmentId: string; onRefreshCourse: () => Promise<void> }) {
  const key = `certification-credit-transfer:${enrollmentId}`
  const generation = useRef(0), sending = useRef(false)
  const [preview, setPreview] = useState<CreditTransferPreview | null>(null)
  const [pending, setPending] = useState<Pending | null>(() => {
    try {
      const value = JSON.parse(localStorage.getItem(key) || 'null')
      return value && validRequest(value.request, enrollmentId) && choiceDigest(value.manifest)
        && typeof value.title === 'string' && Number.isInteger(value.xp) && value.xp >= 0 ? value : null
    } catch { return null }
  })
  const [phase, setPhase] = useState<'review' | 'uncertain' | 'retry' | 'saved' | 'stopped'>(pending ? 'uncertain' : 'review')
  const [consent, setConsent] = useState(false), [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  useEffect(() => () => { ++generation.current }, [enrollmentId])

  async function load() {
    const token = ++generation.current
    setBusy(true); setMessage(''); setConsent(false)
    try {
      const value = await previewCreditTransfer(enrollmentId)
      if (token !== generation.current) return
      if (value.target_enrollment_id !== enrollmentId || value.read_only !== true || value.credit_transferred !== false
        || value.xp_earned !== 0 || !choiceId(value.source_enrollment_id) || !choiceDigest(value.preview_sha256)
        || !choiceDigest(value.target_manifest_sha256) || !Array.isArray(value.modules)
        || new Set(value.modules.map(row => row.module_id)).size !== value.modules.length
        || value.modules.some(row => !Number.isInteger(row.outcome_count) || row.outcome_count <= 0 || row.xp_earned !== 0
          || !Number.isInteger(row.xp_carried) || row.xp_carried < 0
          || (row.eligible && (!row.request || !validRequest(row.request, enrollmentId) || row.completed
            || row.request.source_enrollment_id !== value.source_enrollment_id || row.request.module_id !== row.module_id
            || row.request.preview_sha256 !== value.preview_sha256)))) throw new Error('Transfer preview identity changed')
      setPreview(value); setPending(null); setPhase('review'); localStorage.removeItem(key)
    } catch {
      if (token === generation.current) setMessage('Credit eligibility could not be loaded. Your existing course credit is preserved. Refresh the course and review again.')
    } finally { if (token === generation.current) setBusy(false) }
  }
  function choose(module: TransferModule) {
    if (!preview || !module.request) return
    setPending({ request: module.request, manifest: preview.target_manifest_sha256, title: module.title, xp: module.xp_carried })
    setConsent(false); setMessage(''); setPhase('review')
  }
  async function run(read: boolean) {
    if (!pending || sending.current || (!read && phase === 'review' && !consent)) return
    const token = generation.current
    sending.current = true; setBusy(true); setMessage('')
    try {
      if (!read) {
        try {
          localStorage.setItem(key, JSON.stringify(pending))
          if (localStorage.getItem(key) !== JSON.stringify(pending)) throw new Error('Could not preserve request')
        } catch {
          setPhase('review'); setMessage('Browser storage is unavailable. No transfer was sent. Restore storage before submitting this choice.')
          return
        }
      }
      let result: CompletionResult
      if (read) {
        const saved = await getCreditTransfer(pending.request.request_id)
        if (token !== generation.current) return
        if (saved.read_only !== true || Object.keys(saved.request).length !== Object.keys(pending.request).length
          || Object.entries(pending.request).some(([field, value]) => saved.request[field as keyof CreditTransferRequest] !== value)) throw new Error('Original transfer differs')
        if (saved.state !== 'applied' || !saved.result) {
          if (saved.state === 'failed' || saved.state === 'rejected') {
            setPhase('stopped'); setMessage('The original request ended without applying credit. Review current eligibility before making another choice.')
            return
          }
          setPhase(saved.state === 'graded' ? 'retry' : 'uncertain')
          setMessage(saved.state === 'graded' ? 'The original transfer is prepared. Resume it to finish saving the reviewed credit.'
            : 'This transfer has no confirmed applied result. Refresh the course to inspect pending completion recovery before retrying work.')
          return
        }
        result = saved.result
      } else result = await applyCreditTransfer(pending.request)
      if (token !== generation.current) return
      if (result.attempt_id !== pending.request.request_id || result.enrollment_id !== enrollmentId
        || result.module_id !== pending.request.module_id || result.manifest_sha256 !== pending.manifest
        || result.source_enrollment_id !== pending.request.source_enrollment_id || result.credit_origin !== 'transferred'
        || result.xp_earned !== 0 || result.xp_carried !== pending.xp) throw new Error('Transfer result could not be confirmed')
      localStorage.removeItem(key); setPhase('saved'); setPreview(null)
      setMessage(`${pending.title}: credit recorded, with ${pending.xp} XP carried into this course and 0 new XP earned. Your original credit remains intact.`)
      try { await onRefreshCourse() }
      catch { if (token === generation.current) setMessage('The transfer was saved. Refresh the course to update its progress; do not submit it again.') }
    } catch (error) {
      if (token !== generation.current) return
      if (read && error instanceof ApiError && error.status === 404) {
        setPhase('retry'); setMessage('No saved transfer was found. Retry the original request, or review current eligibility again.')
      } else {
        setPhase('uncertain'); setMessage('The transfer could not be confirmed. Check its saved result before trying again.')
      }
    } finally { sending.current = false; if (token === generation.current) setBusy(false) }
  }
  return <section aria-label="Credit from your original course" className="min-w-0 space-y-3 border-t border-gray-200 pt-4 text-sm text-gray-700 [overflow-wrap:anywhere]">
    <h4 className="font-semibold text-gray-900">Credit from your original course</h4>
    <p>Review evidence-based credit separately from switching courses. A switch alone never transfers credit.</p>
    {(!pending || phase === 'saved' || phase === 'retry' || phase === 'stopped') && <button type="button" disabled={busy} className={choiceButton} onClick={() => { void load() }}>Review credit eligibility</button>}
    {preview && !pending && <><p>{preview.explanation}</p><ul className="space-y-3">{preview.modules.map(module => <li key={module.module_id}>
      <p className="font-semibold text-gray-900">{module.title}</p><p>{module.reason}</p>
      {module.eligible && <button type="button" className={`${choiceButton} mt-2`} onClick={() => choose(module)}>Review transfer: {module.title}</button>}
    </li>)}</ul></>}
    {pending && phase === 'review' && <>
      <p className="font-semibold text-gray-900">Transfer credit for {pending.title}</p>
      <p>{pending.xp} XP carried toward this course’s progress · 0 new XP earned. Original assessments and credit stay in the original course.</p>
      <label className="flex min-h-11 items-start gap-3 py-2"><input type="checkbox" className="mt-1 shrink-0" checked={consent} onChange={event => setConsent(event.target.checked)} /><span>Transfer this module’s reviewed credit while preserving my original course and evidence.</span></label>
      <button type="button" className={choiceButton} disabled={!consent || busy} onClick={() => { void run(false) }}>Transfer reviewed credit</button>
      <button type="button" className={choiceButton} disabled={busy} onClick={() => setPending(null)}>Back to eligibility</button>
    </>}
    <p role="status">{busy ? 'Checking or saving the original transfer…' : message}</p>
    {busy && <p>Closing this panel does not cancel the request. Reopen it and check the saved result.</p>}
    {pending && phase === 'uncertain' && <button type="button" className={choiceButton} disabled={busy} onClick={() => { void run(true) }}>Check saved transfer</button>}
    {pending && phase === 'retry' && <button type="button" className={choiceButton} disabled={busy} onClick={() => { void run(false) }}>Resume original transfer</button>}
    {phase !== 'review' && <button type="button" className={choiceButton} disabled={busy} onClick={() => { void onRefreshCourse().catch(() => setMessage('Course refresh is unavailable. The original transfer remains saved for recovery.')) }}>Refresh course progress</button>}
  </section>
}
