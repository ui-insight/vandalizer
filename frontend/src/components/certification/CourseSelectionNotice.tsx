import { useEffect, useId, useRef, useState } from 'react'
import { confirmCourseSelection, getCourseSelectionStatus, stopCoursePreparation } from '../../api/certification'
import type { CoursePreparationStatus, CourseSelectionReceipt, CourseSelectionStatus } from '../../api/certification'

const buttonStyle = 'min-h-11 min-w-0 max-w-full rounded border border-amber-800 bg-white px-3 py-2 text-left text-sm font-medium text-amber-950 [overflow-wrap:anywhere] disabled:opacity-60'

function verifiedStatus(status: CourseSelectionStatus) {
  if (!status || status.read_only !== true || (status.current_enrollment_id !== null && typeof status.current_enrollment_id !== 'string')) throw new Error('Invalid course status')
  const receipt = status.pending
  if (receipt !== null && (!receipt || !/^[a-f0-9]{32}$/.test(receipt.request_id)
    || !/^[a-f0-9]{64}$/.test(receipt.receipt_sha256)
    || !/^[a-f0-9]{32}$/.test(receipt.source_enrollment_id)
    || !/^[a-f0-9]{32}$/.test(receipt.target_enrollment_id)
    || receipt.source_enrollment_id === receipt.target_enrollment_id
    || receipt.target_enrollment_id !== status.current_enrollment_id
    || typeof receipt.target_course_version !== 'string' || !receipt.target_course_version
    || !Number.isSafeInteger(receipt.revision) || receipt.revision < 1
    || !Number.isFinite(Date.parse(receipt.selected_at))
    || receipt.histories_preserved !== true || receipt.credit_transferred !== false
    || !((receipt.kind === 'optional_upgrade_selection.1' && receipt.action === 'activate_optional_upgrade')
      || (receipt.kind === 'saved_course_selection.1' && ['return_to_original_course', 'resume_upgraded_course'].includes(receipt.action))))) throw new Error('Invalid saved choice')
  const preparation = status.preparation
  if (preparation && (receipt !== null || preparation.read_only !== true || preparation.selection_changed !== false
    || preparation.credit_changed !== false || preparation.enrollment_id !== status.current_enrollment_id
    || !['preparing', 'recovery_pending'].includes(preparation.state)
    || !['activate_optional_upgrade', 'select_saved_course'].includes(preparation.operation)
    || [preparation.request_id, preparation.enrollment_id, preparation.original_request_id, preparation.write_id].some(value => !/^[a-f0-9]{32}$/.test(value))
    || !/^[a-f0-9]{64}$/.test(preparation.preview_sha256)
    || typeof preparation.course_version !== 'string' || !preparation.course_version)) throw new Error('Invalid course preparation')
  return status
}

export function CourseSelectionNotice({ enrollmentId, refreshKey = 0, onRefreshCourse }: {
  enrollmentId?: string
  refreshKey?: number
  onRefreshCourse: () => Promise<void>
}) {
  const headingId = useId()
  const sequence = useRef(0)
  const focus = useRef<HTMLDivElement>(null)
  const [pending, setPending] = useState<CourseSelectionReceipt | null>(null)
  const [preparation, setPreparation] = useState<CoursePreparationStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function read(userInitiated = false) {
    const token = ++sequence.current
    setBusy(true); setError('')
    try {
      const status = verifiedStatus(await getCourseSelectionStatus())
      if (token !== sequence.current) return
      setPending(status.pending)
      setPreparation(status.preparation ?? null)
      setMessage(userInitiated && !status.pending && !status.preparation ? 'No course switch is awaiting confirmation. Refresh your course to load its current saved work.' : '')
    } catch {
      if (token === sequence.current) setError('Your course-switch status could not be checked. Refresh the status before confirming a saved choice.')
    } finally { if (token === sequence.current) setBusy(false) }
  }

  useEffect(() => {
    const lifecycle = sequence
    setPending(null); setPreparation(null); setMessage('')
    void read()
    return () => { ++lifecycle.current }
  }, [enrollmentId, refreshKey])

  async function confirm() {
    if (!pending || busy || error) return
    const original = pending
    const token = ++sequence.current
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await confirmCourseSelection(original)
      if (token !== sequence.current) return
      if (result.confirmed !== true || result.selection_changed !== false
        || !result.receipt || Object.keys(original).some(key => result.receipt[key as keyof CourseSelectionReceipt] !== original[key as keyof CourseSelectionReceipt])) throw new Error('Receipt changed')
      setPending(null)
      setMessage('Your saved course choice is confirmed. Refresh your course to continue from its current saved work.')
    } catch {
      if (token === sequence.current) setError('Confirmation could not be verified. Check the saved status before trying again; your request may already have finished.')
    } finally {
      if (token === sequence.current) {
        setBusy(false)
        requestAnimationFrame(() => { if (token === sequence.current) focus.current?.focus() })
      }
    }
  }

  async function refreshCourse() {
    const token = ++sequence.current
    setBusy(true)
    try { await onRefreshCourse() }
    catch { if (token === sequence.current) setError('Your course could not be refreshed. Try refreshing it again.') }
    finally { if (token === sequence.current) setBusy(false) }
  }

  async function stopPreparation() {
    if (!preparation || busy || error) return
    const original = preparation
    const token = ++sequence.current
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await stopCoursePreparation(original)
      if (token !== sequence.current) return
      if (result.kind !== 'selection_preparation_recovery.1' || result.status !== 'preparation_stopped'
        || result.recovery_id !== original.request_id || result.enrollment_id !== original.enrollment_id
        || result.original_request_id !== original.original_request_id || result.original_write_id !== original.write_id
        || result.selection_changed !== false || result.credit_changed !== false || result.assessments_repeated !== false) throw new Error('Recovery identity changed')
      setPreparation(null)
      setMessage('Course-change preparation stopped. Your course and earned work stay as they were. Refresh your course to continue.')
    } catch {
      if (token === sequence.current) setError('Stopping preparation could not be confirmed. Refresh the saved status before trying again; it may already have finished.')
    } finally {
      if (token === sequence.current) {
        setBusy(false)
        requestAnimationFrame(() => { if (token === sequence.current) focus.current?.focus() })
      }
    }
  }

  if (!pending && !preparation && !error && !message) return null
  return <section aria-labelledby={headingId} className="min-w-0 border-b border-amber-200 bg-amber-50 p-3 text-sm text-amber-950 [overflow-wrap:anywhere] sm:p-4">
    <h3 id={headingId} className="font-semibold">{pending ? 'Finish confirming your course choice' : preparation ? 'Keep your current course' : 'Course choice status'}</h3>
    <div ref={focus} tabIndex={-1} className="mt-2 space-y-2 outline-offset-4">
      {pending && <>
        <p>Your {pending.action === 'return_to_original_course' ? 'return to the original course' : pending.action === 'resume_upgraded_course' ? 'return to the saved upgrade' : 'optional course upgrade'} was saved. Confirm its saved result before starting another course activity.</p>
        <p>Selected version: <span className="font-medium">{pending.target_course_version}</span></p>
        <p>Both courses keep their original work, XP and certificates. Confirmation does not switch courses again or repeat an assessment.</p>
      </>}
      {preparation && <>
        <p>{preparation.state === 'recovery_pending'
          ? 'Stopping your earlier course-change preparation still needs confirmation. Check its saved result to continue.'
          : 'Your course change is still being prepared. You can wait and refresh its status, or stop this preparation to keep learning in your current course.'}</p>
        <p>Current version: <span className="font-medium">{preparation.course_version}</span></p>
        <p>Your saved work, XP and certificates stay with their courses. Stopping this preparation does not restart assessments or workspace jobs.</p>
      </>}
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
    </div>
    <div className="mt-3 flex flex-wrap gap-2">
      {pending && !error && <button type="button" className={buttonStyle} disabled={busy} onClick={() => { void confirm() }}>{busy ? 'Checking saved choice…' : 'Confirm saved course choice'}</button>}
      {preparation && !error && <button type="button" className={buttonStyle} disabled={busy} onClick={() => { void stopPreparation() }}>{busy ? 'Checking saved preparation…' : preparation.state === 'recovery_pending' ? 'Finish stopping preparation' : 'Stop course-change preparation'}</button>}
      <button type="button" className={buttonStyle} disabled={busy} onClick={() => { void read(true) }}>Refresh switch status</button>
      {!pending && !preparation && <button type="button" className={buttonStyle} disabled={busy} onClick={() => { void refreshCourse() }}>Refresh my course</button>}
    </div>
  </section>
}
