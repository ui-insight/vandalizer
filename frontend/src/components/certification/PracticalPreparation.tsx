import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { getPracticalPreparation, preparePracticalRun } from '../../api/certification'
import { listSearchSets } from '../../api/extractions'
import type { PracticalPreparationBody, SavedPracticalPreparation } from '../../types/certification'
import type { SearchSet } from '../../types/workflow'
import { CourseEditorLink } from './CourseEditorLink'

const button = 'min-h-11 min-w-0 max-w-full rounded-lg border border-gray-300 bg-white px-2 py-2 text-left text-sm font-medium text-gray-900 [overflow-wrap:anywhere] disabled:opacity-50 sm:px-4'
const control = 'mt-1 block min-h-11 w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900'
function storedRequest(key: string): PracticalPreparationBody | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) || 'null')
    if (value && /^[a-f0-9]{32}$/.test(value.request_id) && typeof value.artifact_id === 'string' && /^\S{1,200}$/.test(value.artifact_id)) return value
  } catch { /* The submit action explains unavailable storage before sending. */ }
  return null
}

export function PracticalPreparation({ enrollmentId, moduleId, onPrepared, onSaved }: {
  enrollmentId: string; moduleId: string; onPrepared: (runId: string) => void; onSaved?: () => void
}) {
  const key = `certification-preparation:${enrollmentId}:${moduleId}`
  const [pending, setPending] = useState(() => storedRequest(key))
  const pendingRef = useRef(pending)
  const [open, setOpen] = useState(!!pending)
  const [search, setSearch] = useState('')
  const [choices, setChoices] = useState<SearchSet[] | null>(null)
  const [artifactId, setArtifactId] = useState('')
  const [receipt, setReceipt] = useState<SavedPracticalPreparation | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [activity, setActivity] = useState('')
  const sequence = useRef(0)
  const sending = useRef(false)
  const resultRef = useRef<HTMLDivElement>(null)
  const opener = useRef<HTMLButtonElement>(null)
  useEffect(() => () => { sequence.current++ }, [enrollmentId, moduleId])

  async function loadChoices() {
    if (sending.current) return
    const token = ++sequence.current
    setOpen(true); setBusy(true); setError(''); setChoices(null); setArtifactId('')
    setActivity('Loading your extractions…')
    try {
      const values = await listSearchSets({ scope: 'mine', search: search.trim() })
      if (token === sequence.current) setChoices(values.filter(value => value.set_type === 'extraction'))
    } catch { if (token === sequence.current) setError('Your extractions could not be loaded. Try refreshing this list.') }
    finally { if (token === sequence.current) setBusy(false) }
  }

  function verify(value: SavedPracticalPreparation, body: PracticalPreparationBody) {
    if (value.enrollment_id !== enrollmentId || value.module_id !== moduleId || value.request_id !== body.request_id
        || value.input_snapshot_id !== body.request_id || value.artifact_id !== body.artifact_id
        || !['inputs_saved', 'prepared', 'executing', 'completed', 'failed', 'uncertain'].includes(value.state)
        || (value.state === 'inputs_saved' ? value.run_id !== null : value.run_id !== body.request_id)
        || value.can_execute !== false || value.credit_awarded !== false || value.module_completion_eligible !== false) {
      throw new Error('Preparation identity mismatch')
    }
    return value
  }

  async function prepare() {
    if (sending.current) return
    sending.current = true
    const token = ++sequence.current
    setBusy(true); setError('')
    let sent = false
    try {
      const original = pendingRef.current
      const body = original || { request_id: crypto.randomUUID().replaceAll('-', ''), artifact_id: artifactId }
      if (!body.artifact_id) throw new Error('Choose an extraction')
      sessionStorage.setItem(key, JSON.stringify(body))
      pendingRef.current = body; setPending(body)
      let value: SavedPracticalPreparation | undefined
      if (original) {
        setActivity('Checking the saved preparation…')
        try { value = verify(await getPracticalPreparation(enrollmentId, body.request_id), body) }
        catch (failure) { if (!(failure instanceof ApiError && failure.status === 404)) throw failure }
      }
      if (token !== sequence.current) return
      if (!value || value.state === 'inputs_saved') {
        setActivity('Saving inputs and preparing the run…')
        sent = true
        value = verify(await preparePracticalRun(enrollmentId, moduleId, body), body)
      }
      if (token !== sequence.current) return
      setReceipt(value)
      onSaved?.()
      requestAnimationFrame(() => { if (token === sequence.current) resultRef.current?.focus() })
    } catch (failure) {
      if (token !== sequence.current) return
      if (sent && failure instanceof ApiError && failure.status === 422) {
        try {
          sessionStorage.removeItem(key); pendingRef.current = null; setPending(null); setReceipt(null)
          setError(`${failure.message.replace(/[.!?]$/, '')}. This preparation was not saved. Correct your lab or extraction and try again.`)
        } catch { setError('Keep this tab open. The browser could not update its saved preparation reference.') }
      } else setError(pendingRef.current
        ? 'We could not confirm a prepared run. Your original request is preserved in this tab. Check and finish it before starting another preparation.'
        : 'This browser could not preserve the request. Allow session storage before preparing; no request was sent.')
    } finally { sending.current = false; if (token === sequence.current) setBusy(false) }
  }

  function chooseAnother() {
    if (!receipt || receipt.state === 'inputs_saved') return
    try {
      sessionStorage.removeItem(key); pendingRef.current = null; setPending(null); setReceipt(null); setArtifactId(''); setError('')
    } catch { setError('Keep this tab open. The browser could not update its saved preparation reference.') }
  }

  function close() {
    const token = ++sequence.current
    setOpen(false)
    requestAnimationFrame(() => { if (token === sequence.current) opener.current?.focus() })
  }

  return <section className="min-w-0 space-y-3 border-t border-gray-200 pt-4 [overflow-wrap:anywhere]" aria-label="Prepare a practical run">
    <h4 className="text-base font-semibold text-gray-900">Prepare a practical run</h4>
    <p className="text-sm text-gray-700">Choose your extraction after setting up the assigned lab. Preparation saves its current fields, settings and assigned source text. It does not run a model or award credit.</p>
    {!open ? <button ref={opener} type="button" className={button} onClick={() => { if (pending) setOpen(true); else void loadChoices() }}>{pending ? 'Open saved preparation' : 'Choose my extraction'}</button> : <>
      <button type="button" className={button} disabled={busy} onClick={close}>Close preparation</button>
      {!pending && <>
        <form className="space-y-2" onSubmit={event => { event.preventDefault(); void loadChoices() }}>
          <label className="block text-sm text-gray-900">Find my extraction<input className={control} value={search} onChange={event => setSearch(event.target.value)} disabled={busy} /></label>
          <button className={button} disabled={busy}>Search or refresh extractions</button>
        </form>
        <p className="text-sm text-gray-700">Up to 100 results from your current workspace. Create or edit an extraction there, then refresh this list. Search by title to find another result.</p>
        {choices && !choices.length && <p className="text-sm text-gray-700">No matching extractions found.</p>}
        {!!choices?.length && <label className="block text-sm text-gray-900">My extraction
          <select className={control} value={artifactId} disabled={busy} onChange={event => setArtifactId(event.target.value)}>
            <option value="">Choose an extraction</option>
            {choices.map(choice => <option key={choice.uuid} value={choice.uuid} disabled={!choice.item_count}>{choice.title} · {choice.item_count} fields</option>)}
          </select>
        </label>}
        {artifactId && <p className="text-sm text-gray-700">Selected extraction: {choices?.find(choice => choice.uuid === artifactId)?.title}</p>}
        {choices?.filter(choice => choice.uuid === artifactId).map(choice => <CourseEditorLink key={choice.uuid} kind="extraction" artifactId={choice.uuid} title={choice.title} disabled={busy} />)}
        <button type="button" className={button} disabled={busy || !artifactId} onClick={() => { void prepare() }}>Save inputs and prepare for review</button>
      </>}
      {pending && !receipt && <>
        <p className="text-sm text-gray-700">Check the saved state of your original request. If only inputs were saved, this action finishes preparing that same work.</p>
        <button type="button" className={button} disabled={busy} onClick={() => { void prepare() }}>Check and finish saved preparation</button>
      </>}
      {busy && <p role="status" className="text-sm text-gray-700">{activity}</p>}
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      {receipt && <div ref={resultRef} tabIndex={-1} role="region" aria-label="Saved practical preparation" className="min-w-0 space-y-3 border-t border-gray-200 pt-3 outline-offset-4">
        <h5 className="text-sm font-semibold text-gray-900">{receipt.state === 'prepared' ? 'Ready for your scope review' : `Saved run state: ${receipt.state}`}</h5>
        <p className="text-sm text-gray-700">{receipt.artifact_title}</p>
        <p className="text-sm text-gray-700">Saved fields: {receipt.fields.join(', ')}</p>
        <ul className="list-disc pl-5 text-sm text-gray-700">{receipt.documents.map(document => <li key={document.document_id}>{document.assigned_filename}</li>)}</ul>
        <p className="text-sm text-gray-700">Planned models: {receipt.model_names.join(', ') || 'Not resolved yet'}</p>
        <p className="text-sm text-gray-700">Later workspace edits do not replace these saved inputs. Preparation and scope review do not start execution.</p>
        <details className="text-sm text-gray-700"><summary className="min-h-11 cursor-pointer py-2">Preparation reference</summary><p className="break-all">{receipt.request_id}</p></details>
        {receipt.state === 'prepared' && receipt.run_id && <button type="button" className={button} onClick={() => { sequence.current++; onPrepared(receipt.run_id!) }}>Review proposed scope</button>}
        <button type="button" className={button} disabled={busy} onClick={chooseAnother}>Choose another extraction for a new preparation</button>
      </div>}
    </>}
  </section>
}
