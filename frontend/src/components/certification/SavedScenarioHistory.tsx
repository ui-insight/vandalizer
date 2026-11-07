import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { getSavedScenarioHistory, getSavedScenarioHistoryResult } from '../../api/certification'
import type { ScenarioDefinition, ScenarioHistoryList, ScenarioHistoryResult } from '../../types/certification'

const button = 'min-h-11 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-900 disabled:opacity-50'
const dateLabel = (value: string) => { const date = new Date(value); return Number.isNaN(date.getTime()) ? 'Date unavailable' : date.toLocaleString() }

export function SavedScenarioHistory({ enrollmentId, definition }: { enrollmentId: string; definition: ScenarioDefinition }) {
  const [list, setList] = useState<ScenarioHistoryList | null>(null)
  const [result, setResult] = useState<ScenarioHistoryResult | null>(null)
  const [error, setError] = useState('')
  const [listError, setListError] = useState('')
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [reference, setReference] = useState('')
  const request = useRef(0)
  const resultRef = useRef<HTMLDivElement>(null)
  useEffect(() => () => { ++request.current }, [])
  useEffect(() => {
    let active = true
    getSavedScenarioHistory(enrollmentId, definition.module_id).then(value => {
      if (!active) return
      if (value.enrollment_id !== enrollmentId || value.module_id !== definition.module_id || value.bank_sha256 !== definition.bank_sha256 || value.read_only !== true) throw new Error('Mismatched history')
      setList(value); setListError('')
    }).catch(() => { if (active) { setList(null); setListError('Saved scenario results could not be listed. Reload history or open a known reference.') } })
    return () => { active = false }
  }, [enrollmentId, definition, refresh])
  useLayoutEffect(() => { if (result) resultRef.current?.focus() }, [result])
  async function inspect(id: string) {
    const token = ++request.current
    setBusy(true); setResult(null); setError('')
    try {
      const value = await getSavedScenarioHistoryResult(enrollmentId, definition.module_id, id)
      if (token !== request.current) return
      if (value.attempt_id !== id || value.enrollment_id !== enrollmentId || value.module_id !== definition.module_id
        || value.bank_sha256 !== definition.bank_sha256 || value.read_only !== true || value.credit_awarded !== false
        || value.assessment_kind !== 'scenario_recognition' || value.questions.length !== definition.questions.length
        || value.questions.some((question, index) => question.id !== definition.questions[index].id || question.prompt !== definition.questions[index].prompt)) throw new Error('Mismatched result')
      setResult(value)
    } catch { if (token === request.current) setError('This saved scenario result could not be opened for the original course. Check its reference or try again.') }
    finally { if (token === request.current) setBusy(false) }
  }
  return <section aria-label="Saved scenario answers" className="min-w-0 space-y-3 border-t border-gray-200 pt-3">
    <h4 className="text-base font-semibold text-gray-900">Your recorded scenario choices</h4>
    <p className="text-sm text-gray-700">These are the choices and feedback saved at submission. Viewing them does not grade again or award course credit.</p>
    <button type="button" className={button} onClick={() => { ++request.current; setResult(null); setError(''); setList(null); setListError(''); setBusy(false); setRefresh(value => value + 1) }}>Reload scenario history</button>
    {!list && !listError && <p role="status" className="text-sm text-gray-700">Loading saved scenario results…</p>}
    {listError && <p role="alert" className="text-sm text-red-800">{listError}</p>}
    {list && <>
      {list.attempts.length ? <ul className="space-y-2">{list.attempts.map((attempt, index) => <li key={attempt.attempt_id}>
        <button type="button" className={`${button} w-full text-left`} onClick={() => { void inspect(attempt.attempt_id) }}>Open scenario result {index + 1} · {dateLabel(attempt.submitted_at)} · {attempt.passed ? 'Recognition supported' : 'More practice needed'}</button>
      </li>)}</ul> : <p className="text-sm text-gray-700">No saved scenario submissions are available for this module yet.</p>}
      {list.older_attempts_available && <p className="text-sm text-gray-700">Showing the 50 most recent submissions. Older results remain available by reference.</p>}
    </>}
    <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-gray-900">Open a scenario result by reference</summary>
      <form onSubmit={event => { event.preventDefault(); void inspect(reference.trim()) }} className="space-y-2">
        <label className="block text-sm text-gray-900">Full scenario reference<input className="mt-1 block min-h-11 w-full min-w-0 rounded-lg border border-gray-300 p-2" value={reference} onChange={event => setReference(event.target.value)} required pattern="[a-f0-9]{32}" /></label>
        <button className={button}>Open saved scenario result</button>
      </form>
    </details>
    {busy && <p role="status" className="text-sm text-gray-700">Opening saved scenario result…</p>}
    {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
    {result && <div ref={resultRef} tabIndex={-1} role="region" aria-label="Original scenario result" className="min-w-0 space-y-3 border-t border-gray-200 pt-3 outline-offset-4">
      <h5 className="font-semibold text-gray-900">{result.passed ? 'Recognition supported' : 'More practice needed'}</h5>
      <p className="text-sm text-gray-700">Submitted {dateLabel(result.submitted_at)} · No module credit awarded</p>
      <ol className="space-y-4">{result.questions.map((question, index) => <li key={question.id} className="space-y-2 border-t border-gray-200 pt-3 text-sm text-gray-800">
        <h6 className="font-semibold">{index + 1}. {question.prompt}</h6>
        <p>Your recorded choice: {question.chosen_answer ?? 'No answer recorded'}</p>
        <p className="font-medium">{question.passed ? 'Supported choice' : 'Needs another look'}</p>
        <p className="whitespace-pre-wrap">{question.feedback}</p>
      </li>)}</ol>
      <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-gray-700">Scenario submission reference</summary><p className="break-all text-sm text-gray-700">{result.attempt_id}</p></details>
    </div>}
  </section>
}
