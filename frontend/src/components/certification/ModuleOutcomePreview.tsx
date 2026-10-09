import { ApiError } from '../../api/client'
import type { OutcomeCompletionSelection } from '../../types/certification'
import { useEffect, useRef, useState } from 'react'
import { getAutomaticReviews, getSavedScenarioHistory } from '../../api/certification'
import { getModuleReadiness, verifyModuleReadiness, type AssessmentSelection, type ModuleReadinessResult, type ReadinessIdentity } from '../../api/moduleReadiness'

const button = 'min-h-11 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-900 disabled:opacity-50'
const control = 'mt-1 block min-h-11 w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900'
const labels = {
  selection_required: 'Select saved evidence', assessment_pending: 'Assessment pending', grading_unavailable: 'Assessment unavailable',
  revision_required: 'Revision needed', supported: 'Supported by selected evidence', requirements_supported: 'All draft outcomes supported',
}
const reviewLabels = { prepared: 'Awaiting assessment', evaluating: 'No final result yet', requirements_supported: 'Draft requirements supported', revision_required: 'Revision needed', grading_unavailable: 'Assessment unavailable' }
type Choice = { id: string; label: string }
function dateLabel(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? 'Date unavailable' : date.toLocaleString() }

interface Props {
  identity: ReadinessIdentity
  moduleId: string
  onComplete?: (selection: OutcomeCompletionSelection) => Promise<void>
  completed?: boolean
  completionPending?: boolean
  progressRefreshPending?: boolean
}
export function ModuleOutcomePreview(props: Props) {
  return <OutcomeSelection key={`${props.identity.enrollment_id}:${props.identity.manifest_sha256}:${props.moduleId}`} {...props} />
}

function OutcomeSelection({ identity, moduleId, onComplete, completed = false, completionPending = false, progressRefreshPending = false }: Props) {
  const [saving, setSaving] = useState(false)
  const savingRef = useRef(false)
  const [open, setOpen] = useState(false)
  const [baseline, setBaseline] = useState<ModuleReadinessResult | null>(null)
  const [result, setResult] = useState<ModuleReadinessResult | null>(null)
  const [selection, setSelection] = useState<AssessmentSelection>({})
  const [reviews, setReviews] = useState<Choice[]>([])
  const [scenarios, setScenarios] = useState<Choice[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [listError, setListError] = useState('')
  const requests = useRef(0)
  const resultRef = useRef<HTMLDivElement>(null)
  const opener = useRef<HTMLButtonElement>(null)
  useEffect(() => () => { ++requests.current }, [])
  useEffect(() => { if (result) resultRef.current?.focus() }, [result])

  async function completeSelected() {
    if (!onComplete || !result?.all_required_outcomes_supported || completed || completionPending || progressRefreshPending || savingRef.current) return
    savingRef.current = true; setSaving(true); setError('')
    const request = requests.current
    try {
      await onComplete({ ...(selection.review ? { review_attempt_id: selection.review } : {}), ...(selection.scenario ? { scenario_attempt_id: selection.scenario } : {}) })
    } catch (failure) {
      if (request !== requests.current) return
      if (failure instanceof ApiError && failure.status === 400) {
        setResult(null)
        setError('Completion requirements were not met. Review the saved feedback and check your selection again.')
      } else if (failure instanceof Error && failure.message.startsWith('Browser storage is unavailable')) {
        setError(failure.message)
      } else {
        setError('Completion could not be confirmed. Use the pending completion notice to retry the original request before changing evidence.')
      }
    } finally { savingRef.current = false; if (request === requests.current) setSaving(false) }
  }
  async function load() {
    const request = ++requests.current
    setOpen(true); setBusy(true); setError(''); setListError(''); setResult(null)
    try {
      const required = verifyModuleReadiness(await getModuleReadiness(identity.enrollment_id, moduleId), identity, moduleId, {})
      if (request !== requests.current) return
      setBaseline(required)
      const practical = required.outcomes.some(item => item.method !== 'scenario_choice')
      const recognition = required.outcomes.some(item => item.method === 'scenario_choice')
      const lists = await Promise.allSettled([
        practical ? getAutomaticReviews(identity.enrollment_id, moduleId) : Promise.resolve(null),
        recognition ? getSavedScenarioHistory(identity.enrollment_id, moduleId) : Promise.resolve(null),
      ])
      if (request !== requests.current) return
      const validList = (value: { enrollment_id: string; module_id: string; attempts: { attempt_id: string }[] }) => value.enrollment_id === identity.enrollment_id
        && value.module_id === moduleId && Array.isArray(value.attempts) && value.attempts.every(item => /^[a-f0-9]{32}$/.test(item.attempt_id))
      let failed = false
      const [reviewList, scenarioList] = lists
      if (reviewList.status === 'fulfilled' && reviewList.value && validList(reviewList.value)) {
        setReviews(reviewList.value.attempts.map(item => ({ id: item.attempt_id, label: `${dateLabel(item.prepared_at)} · ${reviewLabels[item.status] || 'Result unavailable'}` })))
      } else { setReviews([]); if (practical) failed = true }
      if (scenarioList.status === 'fulfilled' && scenarioList.value && validList(scenarioList.value) && scenarioList.value.read_only === true) {
        setScenarios(scenarioList.value.attempts.map(item => ({ id: item.attempt_id, label: `${dateLabel(item.submitted_at)} · ${item.passed ? 'Recognition supported' : 'Revision needed'}` })))
      } else { setScenarios([]); if (recognition) failed = true }
      if (failed) setListError('Some saved choices could not be loaded. Refresh the choices, or use a full reference from your saved feedback.')
    } catch { if (request === requests.current) { setBaseline(null); setError('Module requirements could not be loaded for this course. Refresh to try again.') } }
    finally { if (request === requests.current) setBusy(false) }
  }

  function choose(kind: keyof AssessmentSelection, value: string) {
    ++requests.current; setBusy(false); setResult(null); setError('')
    setSelection(current => ({ ...current, [kind]: value || undefined }))
  }
  async function inspect() {
    if (!baseline) return
    const request = ++requests.current
    setBusy(true); setError(''); setResult(null)
    try {
      const value = verifyModuleReadiness(await getModuleReadiness(identity.enrollment_id, moduleId, selection), identity, moduleId, selection, baseline)
      if (request === requests.current) setResult(value)
    } catch { if (request === requests.current) setError('The selected evidence could not be checked for this course. Check the references or try again. No assessment was run.') }
    finally { if (request === requests.current) setBusy(false) }
  }
  function close() { ++requests.current; setOpen(false); setBusy(false); setResult(null); setError(''); requestAnimationFrame(() => opener.current?.focus()) }
  const shown = result || baseline
  const invalidReference = Object.values(selection).some(value => value && !/^[a-f0-9]{32}$/.test(value))
  return <section className="mt-6 min-w-0 space-y-3 border-t border-gray-300 pt-4 [overflow-wrap:anywhere]" aria-label="Combined module outcomes">
    <h3 className="text-base font-semibold text-gray-900">Check all module outcomes</h3>
    <p className="text-sm text-gray-700">Choose the saved assessments to compare with every required outcome. No attempt is chosen for you. {onComplete ? 'Checking does not award credit. After all outcomes are supported, complete the module using those selected records.' : 'This draft preview does not run an assessment, award XP or complete the module.'}</p>
    {!open ? <button ref={opener} type="button" className={button} onClick={load}>Choose saved assessments</button> : <>
      <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={busy || saving} onClick={load}>Refresh saved choices</button>
        <button type="button" className={button} disabled={saving} onClick={close}>Close outcome preview</button></div>
      {busy && <p role="status" className="text-sm text-gray-700">Loading saved evidence…</p>}
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      {listError && <p role="alert" className="text-sm text-red-700">{listError}</p>}
      {baseline && <form className="space-y-4" onSubmit={event => { event.preventDefault(); void inspect() }}>
        {(['review', 'scenario'] as const).map(kind => {
          if (!baseline.outcomes.some(item => (item.method === 'scenario_choice') === (kind === 'scenario'))) return null
          const choices = kind === 'review' ? reviews : scenarios
          const name = kind === 'review' ? 'Automatic assessment' : 'Scenario assessment'
          return <div key={kind} className="min-w-0 space-y-2">
            <label className="block text-sm font-medium text-gray-900">{name}
              <select className={control} disabled={busy || saving} value={selection[kind] || ''} onChange={event => choose(kind, event.target.value)}>
                <option value="">No assessment selected</option>
                {selection[kind] && !choices.some(item => item.id === selection[kind]) && <option value={selection[kind]}>Reference entered below</option>}
                {choices.map((item, index) => <option key={item.id} value={item.id}>{index + 1}. {item.label}</option>)}
              </select>
            </label>
            {selection[kind] && <p className="text-sm text-gray-700">Selected {name.toLowerCase()}: {choices.find(item => item.id === selection[kind])?.label || selection[kind]}</p>}
            {!choices.length && <p className="text-sm text-gray-700">No recent choices are available.</p>}
            <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-gray-700">Use an older {name.toLowerCase()} reference</summary>
              <p className="text-sm text-gray-700">Recent lists may omit older work. Copy the full reference from the original saved feedback.</p>
              <label className="block text-sm text-gray-900">{name} reference
                <input className={control} pattern="[a-f0-9]{32}" disabled={busy || saving} value={selection[kind] || ''} onChange={event => choose(kind, event.target.value.trim())} />
              </label>
            </details>
          </div>
        })}
        {invalidReference && <p className="text-sm text-red-700">Use the complete 32-character reference from your saved feedback.</p>}
        <button className={button} disabled={busy || saving || invalidReference}>Check selected assessments</button>
      </form>}
      {shown && <div ref={resultRef} tabIndex={-1} role="region" aria-label="Module outcome result" className="space-y-3 rounded-lg border border-gray-300 p-3 outline-offset-4">
        <h4 className="text-base font-semibold text-gray-900">{result ? onComplete && result.status === 'requirements_supported' ? 'All required outcomes supported' : labels[result.status] : 'Evidence required for this module'}</h4>
        {!result && <p className="text-sm text-gray-700">Choose evidence, then check your selection to see its result.</p>}
        <ul className="space-y-3">{shown.outcomes.map(item => <li key={item.outcome_id} className="text-sm text-gray-900">
          <p>{item.statement}</p><p className="mt-1 font-semibold">{labels[item.state]}</p>
        </li>)}</ul>
        {result && <><p className="text-sm text-gray-700">This is feedback on the exact selected records. Use the original assessment feedback for details or needed revisions. {completed ? 'Module completion is recorded in your course progress.' : 'This check has not awarded credit.'}</p>
          {onComplete && <div className="space-y-2">
            {completed ? <p role="status" className="text-sm font-semibold text-gray-900">Module complete</p> : <>
              {progressRefreshPending && <p role="status" className="text-sm text-gray-700">Completion is saved. Use the progress refresh notice to update your course status.</p>}
              {completionPending && !saving && <p role="status" className="text-sm text-gray-700">A completion is awaiting confirmation. Retry it from the pending completion notice.</p>}
              <button type="button" className={button} disabled={busy || saving || completionPending || progressRefreshPending || !result.all_required_outcomes_supported} onClick={completeSelected}>
                {saving ? 'Recording module completion…' : 'Complete module with selected evidence'}
              </button>
              <p className="text-sm text-gray-700">Completion checks these original records and required prior modules. It does not run another assessment.</p>
            </>}
          </div>}
          <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-gray-700">Selected evidence details</summary>
            <ul className="space-y-2 text-sm text-gray-700">{result.selected_receipts.map(item => <li key={item.kind}>{item.kind === 'automatic_review' ? 'Automatic assessment' : 'Scenario assessment'}: <span className="break-all">{item.attempt_id}</span></li>)}</ul>
          </details></>}
      </div>}
    </>}
  </section>
}
