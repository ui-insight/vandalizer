import { useEffect, useId, useRef, useState } from 'react'
import { getUpgradeOptions, getUpgradePreview } from '../../api/certification'
import { ApiError } from '../../api/client'
import { OptionalUpgradeChoice } from './OptionalUpgradeChoice'
import type { UpgradeCourseOption, UpgradeOptions, UpgradePreview } from '../../types/certification'

const buttonStyle = 'min-h-11 min-w-0 max-w-full rounded-md border border-gray-300 bg-white px-2 py-2 text-left text-sm font-medium text-gray-900 [overflow-wrap:anywhere] disabled:opacity-50 sm:px-3'

export function UpgradeComparison({ enrollmentId, onRefreshCourse }: { enrollmentId: string; onRefreshCourse: () => Promise<void> }) {
  const headingId = useId()
  const request = useRef(0)
  const openButton = useRef<HTMLButtonElement>(null)
  const resultRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [options, setOptions] = useState<UpgradeOptions | null>(null)
  const [preview, setPreview] = useState<UpgradePreview | null>(null)
  const [error, setError] = useState('')
  const [stale, setStale] = useState(false)
  useEffect(() => () => { ++request.current }, [enrollmentId])

  function failed(reason: unknown) {
    const changed = reason instanceof ApiError && reason.status === 409
    setStale(changed)
    setError(changed
      ? 'Your course or saved work changed. Refresh your course before comparing again.'
      : 'The comparison could not be loaded. Your current course and earned work have not changed.')
  }

  async function loadOptions() {
    const token = ++request.current
    setOpen(true); setBusy(true); setPreview(null); setOptions(null); setError(''); setStale(false)
    try {
      const result = await getUpgradeOptions(enrollmentId)
      if (token !== request.current) return
      if (result.enrollment_id !== enrollmentId || result.policy !== 'optional' || result.can_activate !== false) throw new Error('Comparison identity changed')
      setOptions(result)
    } catch (reason) { if (token === request.current) failed(reason) }
    finally { if (token === request.current) setBusy(false) }
  }

  async function compare(course: UpgradeCourseOption) {
    const token = ++request.current
    setBusy(true); setPreview(null); setError(''); setStale(false)
    try {
      const result = await getUpgradePreview(enrollmentId, course.course_version)
      if (token !== request.current) return
      if (result.source.enrollment_id !== enrollmentId || result.target.course_version !== course.course_version
          || result.target.manifest_sha256 !== course.manifest_sha256 || result.policy !== 'optional' || result.can_activate !== false) throw new Error('Comparison identity changed')
      const plan = result.preservation_plan
      if (plan && (plan.source_enrollment_id !== enrollmentId || plan.policy !== 'retain_with_original_enrollment'
        || plan.read_only !== true || plan.can_activate !== false || plan.credit_transferred !== false
        || !/^[a-f0-9]{64}$/.test(plan.plan_sha256) || !Array.isArray(plan.entries)
        || plan.reconciliation_required_count !== plan.entries.filter(item => item.reconciliation_required).length
        || plan.entries.some(item => !item.record_id || !item.module_id || !item.module_title || !item.label || !item.explanation
          || !['retain_saved_work', 'reconcile_operation', 'retain_unexecuted_work', 'retain_unassessed_work', 'retain_original_result'].includes(item.proposed_action)
          || item.reconciliation_required !== (item.proposed_action === 'reconcile_operation')))) throw new Error('Preservation plan changed')
      setPreview(result)
      requestAnimationFrame(() => { if (token === request.current) resultRef.current?.focus() })
    } catch (reason) { if (token === request.current) failed(reason) }
    finally { if (token === request.current) setBusy(false) }
  }

  function close() {
    const token = ++request.current
    setOpen(false); setBusy(false); setPreview(null); setOptions(null); setError('')
    requestAnimationFrame(() => { if (token === request.current) openButton.current?.focus() })
  }

  async function refreshCourse() {
    close()
    try { await onRefreshCourse() }
    catch { setOpen(true); setError('Your course could not be refreshed. Keep your current work and try again.'); setStale(true) }
  }

  return <section className="my-4 min-w-0 rounded-lg border border-gray-200 bg-white p-2 [overflow-wrap:anywhere] sm:p-4" aria-labelledby={headingId}>
    <h3 id={headingId} className="text-sm font-semibold text-gray-900">Course versions are your choice</h3>
    <p className="mt-1 text-sm text-gray-700">Keep learning in your current course. You can compare an offered version without changing your enrollment or earned work.</p>
    {!open ? <button ref={openButton} type="button" className={`${buttonStyle} mt-3`} onClick={() => { void loadOptions() }}>Compare course versions</button> : <div className="mt-3 space-y-4">
      <button type="button" className={buttonStyle} onClick={close}>Close course options</button>
      {busy && <p role="status" className="text-sm text-gray-700">Loading course comparison…</p>}
      {error && <div role="alert" className="space-y-2 text-sm text-red-800"><p>{error}</p><button type="button" className={buttonStyle} onClick={() => { if (stale) void refreshCourse(); else void loadOptions() }}>{stale ? 'Refresh my course' : 'Retry comparison'}</button></div>}
      {!busy && !error && options?.courses.length === 0 && <p className="text-sm text-gray-700">No other course version is currently offered for your enrollment. Your current course remains selected.</p>}
      {options && options.courses.length > 0 && <ul className="space-y-3">{options.courses.map(course => <li key={course.course_version} className="min-w-0 rounded border border-gray-200 p-2 sm:p-3">
        <p className="break-words text-sm font-semibold text-gray-900">{course.course_title}</p>
        <p className="mt-1 break-words text-sm text-gray-700">Course version: {course.course_version}</p>
        <p className="mt-1 break-words text-sm text-gray-700">{course.description}</p>
        <button type="button" className={`${buttonStyle} mt-2 max-w-full break-words`} disabled={busy} onClick={() => { void compare(course) }}>Compare {course.course_title}</button>
      </li>)}</ul>}
      {preview && <div ref={resultRef} tabIndex={-1} role="region" className="min-w-0 space-y-4 border-t border-gray-300 pt-3 outline-offset-4 sm:rounded sm:border sm:p-3" aria-label="Course version comparison">
        <h4 className="text-base font-semibold text-gray-900">Your course comparison</h4>
        <p className="text-sm text-gray-700">Comparing does not switch courses. You can keep learning here or review an optional upgrade choice. You do not need to decide now.</p>
        <div className="min-w-0 space-y-2 text-sm text-gray-700">
          <h5 className="font-semibold text-gray-900">What stays with your current course</h5>
          <p className="break-words">{preview.source.course_title} · {preview.source.total_xp} XP earned</p>
          <p className="break-words">Course version: {preview.source.course_version}</p>
          {preview.source.provenance === 'legacy_version_unknown' && <p>Your earlier course version was not recorded. Existing earned credit is preserved without claiming which historical lessons you completed.</p>}
          {preview.source.completed_modules.length ? <ul className="list-disc space-y-1 pl-5">{preview.source.completed_modules.map(module => <li key={module.module_id} className="break-words">{module.title} — {module.xp_earned} XP{module.completed_at ? ` · completed ${module.completed_at.slice(0, 10)}` : ' · original completion date unavailable'}</li>)}</ul> : <p>No completed modules are recorded in this enrollment yet.</p>}
          {preview.source.has_saved_place && <p>Your saved reading place remains in this course.</p>}
          {preview.source.credential_preserved && <p>Your original earned certificate remains available in certificate history. It does not become a certificate for the other course.</p>}
          {preview.credential_needs_preservation && <p>Your original certificate still needs to be preserved before any future switch. Its existing completion record has not changed.</p>}
        </div>
        <div className="space-y-2 text-sm text-gray-700">
          <h5 className="break-words font-semibold text-gray-900">Requirements in {preview.target.course_title}</h5>
          <p className="break-words">Course version: {preview.target.course_version}</p>
          <p>{preview.target.required_outcome_count} required outcomes · {preview.target.transferred_outcome_count} confirmed for transfer</p>
          <p>No outcome equivalence has been confirmed for this course pair. Existing XP stays earned in your current course; matching lesson names do not prove the other course’s skills.</p>
          {preview.target.modules.map(module => <details key={module.module_id} className="min-w-0 border-t border-gray-200 py-2 sm:rounded sm:border sm:p-3">
            <summary className="min-h-11 cursor-pointer break-words font-medium text-gray-900">{module.title} — {module.outcomes.length} outcomes to assess</summary>
            <ul className="mt-2 list-disc space-y-2 pl-5">{module.outcomes.map(outcome => <li key={outcome.outcome_id} className="break-words">{outcome.statement}</li>)}</ul>
          </details>)}
        </div>
        {(preview.saved_work.length > 0 || preview.work_in_flight || preview.unfinished_answers) && <div className="space-y-2 text-sm text-gray-700">
          <h5 className="font-semibold text-gray-900">Work that stays in this course</h5>
          {preview.saved_work.length > 0 && <ul className="list-disc space-y-1 pl-5">{preview.saved_work.map(item => <li key={item.kind}>{item.label}: {item.count}</li>)}</ul>}
          {preview.work_in_flight && <p>A course operation is still in progress. Check its result before retrying work or planning a switch.</p>}
          {preview.unfinished_answers && <p>You have unfinished reflection answers saved in your current course.</p>}
          <p>Saved work needs a preservation decision before a future switch. Nothing in this comparison discards it or reruns it.</p>
        </div>}
        {preview.preservation_plan && preview.preservation_plan.entries.length > 0 && <details className="min-w-0 border-t border-gray-200 py-2 text-sm text-gray-700">
          <summary className="min-h-11 cursor-pointer py-2 font-semibold text-gray-900">Saved work preservation plan</summary>
          <p className="mt-2">This is a proposed plan. Every record stays with its original enrollment. Nothing is moved, deleted, reassessed or executed.</p>
          {preview.preservation_plan.reconciliation_required_count > 0 && <p className="mt-2 font-semibold text-gray-900">{preview.preservation_plan.reconciliation_required_count} saved operations need resolution before a future switch. A stopped connection does not prove an operation stopped.</p>}
          <ul className="mt-3 space-y-4">{preview.preservation_plan.entries.map(item => <li key={`${item.kind}:${item.record_id}`}>
            <p className="font-semibold text-gray-900">{item.label} · {item.module_title}</p>
            <p className="mt-1">{item.explanation}</p>
            <details><summary className="min-h-11 cursor-pointer py-2">Original work reference</summary><p className="break-all">{item.record_id}</p></details>
          </li>)}</ul>
        </details>}
        <OptionalUpgradeChoice key={preview.preview_sha256} preview={preview} onRefreshCourse={refreshCourse} />
        <button type="button" className={buttonStyle} onClick={close}>Close comparison</button>
      </div>}
    </div>}
  </section>
}
