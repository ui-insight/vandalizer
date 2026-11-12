import { useEffect, useRef, useState } from 'react'
import { getScenarioSubmission, submitScenarios } from '../../api/certification'
import { ApiError } from '../../api/client'
import type { ScenarioDefinition, ScenarioResult } from '../../types/certification'

interface Draft {
  answers: Record<string, string>
  pendingId?: string
  lastAttemptId?: string
}

function readDraft(key: string): Draft {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) || 'null')
    if (value && typeof value.answers === 'object' && value.answers !== null && !Array.isArray(value.answers)
      && Object.values(value.answers).every(answer => typeof answer === 'string')
      && [value.pendingId, value.lastAttemptId].every(id => id === undefined || /^[a-f0-9]{32}$/.test(id))) return value
  } catch { /* A blocked browser store is explained before any submission. */ }
  return { answers: {} }
}

/** The parent keys this component by enrollment and bank digest. Never auto-submit. */
export function ScenarioAssessment({ definition, enrollmentId, attemptId, onSaved }: {
  definition: ScenarioDefinition
  enrollmentId: string
  attemptId?: string
  onSaved?: () => Promise<void>
}) {
  const storageKey = `certification-scenarios:${enrollmentId}:${definition.module_id}:${definition.bank_sha256}`
  const [draft, setDraft] = useState(() => readDraft(storageKey))
  const draftRef = useRef(draft)
  const [busy, setBusy] = useState(false)
  const [checking, setChecking] = useState(false)
  const [retryKind, setRetryKind] = useState<'missing' | 'unlinked' | null>(null)
  const sending = useRef(false)
  const confirmed = useRef(false)
  const [error, setError] = useState('')
  const [historyError, setHistoryError] = useState('')
  const [reload, setReload] = useState(0)
  const [saved, setSaved] = useState<{ id: string; result: ScenarioResult; older?: boolean; reused?: boolean } | null>(null)
  const resultRef = useRef<HTMLDivElement>(null)
  const questionGroups = useRef<Record<string, HTMLFieldSetElement | null>>({})
  const historyId = attemptId || draft.lastAttemptId

  useEffect(() => {
    if (!historyId || draft.pendingId || confirmed.current) return
    let active = true
    getScenarioSubmission(historyId).then(record => {
      if (!active) return
      if (record.enrollment_id !== enrollmentId || record.module_id !== definition.module_id || record.bank_sha256 !== definition.bank_sha256) {
        setHistoryError('The saved result belongs to different course requirements. Refresh your course before continuing.')
        return
      }
      setSaved({ id: record.uuid, result: record.result, older: record.progress_link === 'superseded' })
      setHistoryError('')
      // Keep unsent edits, including edits made while this request was loading.
      if (!Object.keys(draftRef.current.answers).length) {
        const next = { ...draftRef.current, answers: record.answers }
        draftRef.current = next
        setDraft(next)
      }
    }).catch(() => { if (active) setHistoryError('Your saved result could not be loaded. Your answers are still available.') })
    return () => { active = false }
  }, [historyId, draft.pendingId, enrollmentId, definition.module_id, definition.bank_sha256, reload])

  function store(next: Draft) {
    // Keep the request identity and exact choices before sending anything.
    sessionStorage.setItem(storageKey, JSON.stringify(next))
    draftRef.current = next
    setDraft(next)
  }

  function choose(questionId: string, choiceId: string) {
    const next = { ...draftRef.current, answers: { ...draftRef.current.answers, [questionId]: choiceId } }
    draftRef.current = next
    setDraft(next)
    try { store(next); setError('') } catch { setError('This browser could not save your draft. Allow session storage before submitting; keep this page open to retain your choices.') }
  }

  async function submit() {
    if (sending.current || (draftRef.current.pendingId && !retryKind)) return
    sending.current = true
    setRetryKind(null)
    setBusy(true)
    setError('')
    try {
      const pending = { ...draftRef.current, pendingId: draftRef.current.pendingId || crypto.randomUUID().replaceAll('-', '') }
      store(pending)
      const response = await submitScenarios(enrollmentId, definition.module_id, pending.pendingId, definition.bank_sha256, pending.answers)
      confirmed.current = true
      setSaved({ id: response.attempt_id, result: response.result, older: !response.linked_to_progress, reused: response.reused_existing === true })
      store({ answers: pending.answers, lastAttemptId: response.attempt_id })
      requestAnimationFrame(() => resultRef.current?.focus())
      try { await onSaved?.() } catch { setError('Your scenario result was saved. Refresh the course to update its progress display.') }
    } catch {
      setError(draftRef.current.pendingId
        ? 'We could not confirm this submission. Your exact choices and reference are saved in this browser tab. Check the saved result before changing answers.'
        : 'This browser could not preserve your submission. Allow session storage before submitting; keep this page open to retain your choices.')
    } finally {
      sending.current = false
      setBusy(false)
    }
  }

  async function checkSaved() {
    const pending = draftRef.current
    if (sending.current || !pending.pendingId) return
    sending.current = true
    setBusy(true)
    setChecking(true)
    setError('')
    setRetryKind(null)
    try {
      const record = await getScenarioSubmission(pending.pendingId)
      const sameAnswers = Object.keys(record.answers).length === Object.keys(pending.answers).length
        && Object.entries(pending.answers).every(([key, value]) => record.answers[key] === value)
      if (record.uuid !== pending.pendingId || record.enrollment_id !== enrollmentId
        || record.module_id !== definition.module_id || record.bank_sha256 !== definition.bank_sha256 || !sameAnswers) {
        setError('The saved result does not match this submission. Keep your original choices and reference; reload the course before continuing.')
        return
      }
      setSaved({ id: record.uuid, result: record.result, older: record.progress_link === 'superseded' })
      requestAnimationFrame(() => resultRef.current?.focus())
      if (record.progress_link === 'selected' || record.progress_link === 'superseded') {
        confirmed.current = true
        store({ answers: pending.answers, lastAttemptId: record.uuid })
        try { await onSaved?.() } catch { setError('Your scenario result was saved. Refresh the course to update its progress display.') }
      } else if (record.progress_link === 'unlinked') {
        setRetryKind('unlinked')
        setError('Your result is saved, but linking it to course progress did not finish. Finish linking uses the original submission; it cannot replace a newer result.')
      } else {
        setError('Your result is saved, but its course progress could not be confirmed. Keep this reference and reload the course before continuing.')
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setRetryKind('missing')
        setError('No saved result was found for this reference. You can explicitly retry the original submission with the same choices and reference.')
      } else {
        setError('We could not check your saved result. Your choices and reference remain locked; try the read-only check again when your connection or session is restored.')
      }
    } finally {
      sending.current = false
      setBusy(false)
      setChecking(false)
    }
  }

  const answered = definition.questions.filter(question => question.choices.some(choice => draft.answers[question.id] === choice.id)).length
  return <section className="mb-6 max-w-3xl space-y-4" aria-label="Scenario assessment">
    <div>
      <h4 className="text-base font-semibold text-gray-900">Practice your judgment</h4>
      <p className="mt-1 text-sm text-gray-700">Choose how you would respond in each scenario. Every case is required. Your submitted choices and feedback are saved; this recognition assessment does not award module credit or XP.</p>
      <p className="mt-2 text-sm text-gray-600">{answered} of {definition.questions.length} answered · Drafts stay in this browser tab until you submit.</p>
    </div>
    {historyError && <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
      <p>{historyError}</p><button type="button" onClick={() => setReload(value => value + 1)} className="mt-2 min-h-11 underline">Reload saved result</button>
    </div>}
    <form onSubmit={event => { event.preventDefault(); void (draftRef.current.pendingId ? checkSaved() : submit()) }} className="space-y-4">
      {definition.questions.map((question, index) => <fieldset key={question.id} ref={element => { questionGroups.current[question.id] = element }} disabled={busy || !!draft.pendingId} className="min-w-0 rounded-lg border border-gray-200 p-4">
        <legend className="max-w-full px-1 text-sm font-semibold leading-relaxed text-gray-900">{index + 1}. {question.prompt}</legend>
        <div className="mt-2 space-y-2">{question.choices.map(choice => <label key={choice.id} className="flex min-h-11 cursor-pointer items-start gap-3 rounded-md border border-gray-200 p-3 text-sm leading-relaxed text-gray-800 has-checked:border-highlight-text has-checked:bg-highlight/20 has-focus-visible:outline-2 has-focus-visible:outline-offset-2">
          <input type="radio" required name={`${definition.bank_id}:${question.id}`} value={choice.id} checked={draft.answers[question.id] === choice.id} onChange={() => choose(question.id, choice.id)} className="mt-1 size-4 shrink-0 accent-highlight-text" />
          <span className="min-w-0 break-words">{choice.text}</span>
        </label>)}</div>
      </fieldset>)}
      {draft.pendingId && <p role="status" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">Submission awaiting confirmation. Checking reads the saved result without submitting again. <span className="block break-all">Reference: {draft.pendingId}</span></p>}
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={busy || (!draft.pendingId && answered !== definition.questions.length)} className="min-h-11 rounded-lg bg-highlight px-4 py-2 text-sm font-semibold text-highlight-text disabled:opacity-50">{busy ? checking ? 'Checking saved result…' : 'Saving choices…' : draft.pendingId ? 'Check saved scenario result' : 'Submit scenario choices'}</button>
        {draft.pendingId && retryKind && <button type="button" disabled={busy} onClick={() => { void submit() }} className="min-h-11 rounded-lg border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-900 disabled:opacity-50">{retryKind === 'unlinked' ? 'Finish linking saved result' : 'Retry original submission'}</button>}
      </div>
    </form>
    {saved && <div ref={resultRef} tabIndex={-1} className="space-y-3 rounded-lg border border-gray-200 p-4 outline-offset-4" aria-label="Saved scenario result">
      <h4 className="font-semibold text-gray-900">{saved.result.passed ? 'All scenario requirements met' : 'Some scenario requirements need another look'}</h4>
      <p className="text-sm text-gray-700">Feedback applies to the choices saved with this result. Submit revised choices to check them; identical choices reuse their original result. No module credit or XP was awarded.</p>
      {saved.reused && <p role="status" className="text-sm text-gray-700">These exact choices already have a saved result. Showing the original attempt without creating another assessment.</p>}
      {saved.older && <p className="text-sm text-amber-900">This is an earlier submission. A newer result remains selected in your course.</p>}
      <p className="break-all text-xs text-gray-600">Submission reference: {saved.id}</p>
      <ol className="space-y-4">{saved.result.checks.map((check, index) => <li key={check.id} className="space-y-2 text-sm text-gray-700">
        <p className="font-semibold">Scenario {index + 1}: {check.passed ? 'Requirement met' : 'Review needed'}</p>
        <p>{definition.questions.find(question => question.id === check.id)?.prompt}</p>
        <p>{check.detail}</p>
        {!check.passed && <button type="button" disabled={busy || !!draft.pendingId} className="min-h-11 rounded-lg border border-gray-300 bg-white px-3 py-2 font-semibold text-gray-900 disabled:opacity-50" onClick={() => {
          const group = questionGroups.current[check.id]
          const input = group?.querySelector<HTMLInputElement>('input:checked') || group?.querySelector<HTMLInputElement>('input')
          input?.focus()
        }}>Review scenario {index + 1}</button>}
      </li>)}</ol>
    </div>}
  </section>
}
