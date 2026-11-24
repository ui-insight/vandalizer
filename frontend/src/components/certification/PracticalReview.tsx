import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { SavedAutomaticReviews } from './SavedAutomaticReviews'
import { PracticalPreparation } from './PracticalPreparation'
import { PracticalExecution } from './PracticalExecution'
import { PracticalAssessment } from './PracticalAssessment'
import { ApiError } from '../../api/client'
import { getPracticalDecision, getPracticalDecisionContext, getPracticalRuns, submitPracticalDecision } from '../../api/certification'
import type { CertExercise, PracticalDecisionBody, PracticalDecisionContext, PracticalDecisionPrompt, PracticalValueCheck, SavedPracticalDecision, RepairAssignment } from '../../types/certification'

const control = 'mt-1 block min-h-11 w-full min-w-0 rounded-lg border border-gray-300 bg-white p-3 text-sm text-gray-900'
const button = 'min-h-11 rounded-lg bg-highlight px-4 py-2 text-sm font-semibold text-highlight-text disabled:opacity-50'

export function PracticalReview({ enrollmentId, moduleId, prompts, prepareEnabled = false, historyOnly = false, repairAssignment, assignment }: {
  enrollmentId: string; moduleId: string; prompts: PracticalDecisionPrompt[]; prepareEnabled?: boolean; historyOnly?: boolean; repairAssignment?: RepairAssignment; assignment?: CertExercise | null
}) {
  const [runs, setRuns] = useState<{ run_id: string; state: string }[]>([])
  const [older, setOlder] = useState(false)
  const [runId, setRunId] = useState('')
  const [reference, setReference] = useState('')
  const [promptId, setPromptId] = useState(prompts[0]?.id || '')
  const [context, setContext] = useState<PracticalDecisionContext | null>(null)
  const [error, setError] = useState('')
  const [runError, setRunError] = useState('')
  const [loading, setLoading] = useState(true)
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [readOnlyReason, setReadOnlyReason] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [feedback, setFeedback] = useState<{ id: string; revision: number } | null>(null)
  const preparedFocus = useRef(false)
  const reviewRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    let active = true
    getPracticalRuns(enrollmentId, moduleId).then(result => {
      if (!active) return
      if ((result.enrollment_id !== undefined && result.enrollment_id !== enrollmentId) || (result.module_id !== undefined && result.module_id !== moduleId)) {
        setRunError('The saved runs belong to different course requirements. Reload your course.'); setLoading(false); return
      }
      setRuns(result.runs); setOlder(result.older_runs_available); setReadOnlyReason(result.read_only_reason || null); setRunError(''); setLoading(false); setHistoryLoaded(true)
    }).catch(() => { if (active) { setRunError('Saved runs could not be loaded. Try loading them again.'); setLoading(false) } })
    return () => { active = false }
  }, [enrollmentId, moduleId, refresh])
  useEffect(() => {
    if (!runId || !promptId) return
    let active = true
    getPracticalDecisionContext(enrollmentId, moduleId, promptId, runId).then(result => {
      if (!active) return
      const expected = prompts.find(prompt => prompt.id === promptId)
      if (result.enrollment_id !== enrollmentId || result.module_id !== moduleId || result.run_id !== runId
        || result.prompt.id !== promptId || result.prompt.prompt_sha256 !== expected?.prompt_sha256
        || (moduleId === 'extraction_engine' && !result.repair_case)
        || (result.repair_case && (result.repair_case.case.module_id !== moduleId
          || result.repair_case.case.baseline.provenance !== 'authored_flawed_example_not_an_execution'
          || !/^[a-f0-9]{64}$/.test(result.repair_case.repair_case_sha256)
          || !result.documents.some(document => document.document_id === result.repair_case?.source_document_id)))) {
        setError('The saved work belongs to different course requirements. Reload your course.'); return
      }
      setContext(result); setError('')
    }).catch(() => { if (active) setError('This saved run could not be opened for the selected course. Check its reference or reload.') })
    return () => { active = false }
  }, [enrollmentId, moduleId, promptId, runId, prompts, refresh])
  useLayoutEffect(() => {
    if (context && preparedFocus.current && reviewRef.current) {
      preparedFocus.current = false
      reviewRef.current.focus()
    }
  }, [context])
  function selectRun(value: string) { preparedFocus.current = false; setContext(null); setError(''); setRunId(value) }
  const canAct = !historyOnly && prepareEnabled && historyLoaded && !runError && !error && !readOnlyReason && !context?.read_only_reason
  const reason = historyOnly ? 'You are viewing saved history. Return to your selected course to continue work.' : readOnlyReason || context?.read_only_reason || (runError ? 'Saved history could not be refreshed. Reload saved runs before submitting.' : null)
  const formContext = context && reason ? { ...context, can_submit: false, read_only_reason: reason } : context
  return <section className="mb-6 max-w-3xl space-y-4 [overflow-wrap:anywhere]" aria-label="Practical review">
    <h4 className="text-base font-semibold text-gray-900">Review your saved work</h4>
    <p className="text-sm text-gray-700">{historyOnly ? 'Inspect the original sources, extracted values, decisions and automatic feedback saved for this course. Opening history keeps your current course selected.' : 'Inspect the source and extraction saved for your run, then record your own decision. Saving a review does not start a run or award module credit.'}</p>
    {!historyOnly && moduleId === 'foundations' && assignment?.assessment_method === 'owned_scoped_extraction' && <details open className="min-w-0 border-y border-gray-200 py-3 text-sm text-gray-800">
      <summary className="min-h-11 cursor-pointer py-2 font-semibold text-gray-900">Your Foundations assignment</summary>
      <p className="my-3 leading-relaxed">{assignment.overview}</p>
      <ol className="list-outside list-decimal space-y-3 pl-5 leading-relaxed">
        {assignment.instructions.map((step, index) => <li key={index}>{step}</li>)}
      </ol>
    </details>}
    {readOnlyReason && <p role="status" className="rounded-lg border border-gray-200 p-3 text-sm text-gray-700">{readOnlyReason}</p>}
    {!historyOnly && !runId && repairAssignment?.module_id === moduleId && <RepairExample definition={repairAssignment} />}
    {canAct && <PracticalPreparation key={`preparation:${enrollmentId}:${moduleId}`} enrollmentId={enrollmentId} moduleId={moduleId} onSaved={() => {
      setLoading(true); setRunError(''); setRefresh(current => current + 1)
    }} onPrepared={value => {
      selectRun(value); preparedFocus.current = true; setPromptId(prompts.find(prompt => prompt.phase === 'before_execution')?.id || prompts[0]?.id || ''); setRefresh(current => current + 1)
    }} />}
    {loading && <p role="status" className="text-sm text-gray-600">Loading saved runs…</p>}
    {!loading && !runs.length && !runError && <p className="rounded-lg border border-gray-200 p-4 text-sm text-gray-700">No assessed runs are saved for this module yet. Your review will be available here when a run is prepared.</p>}
    {runError && <p role="alert" className="text-sm text-red-700">{runError}</p>}
    <button type="button" className="min-h-11 text-sm text-gray-700 underline" onClick={() => { setContext(null); setRefresh(value => value + 1) }}>Reload saved runs</button>
    {runs.length > 0 && <label className="block text-sm font-medium text-gray-900">Saved run
      <select className={control} value={runId} onChange={event => selectRun(event.target.value)}>
        <option value="">Choose a saved run</option>
        {runs.map((run, index) => <option key={run.run_id} value={run.run_id}>Run {index + 1} · {run.state} · {run.run_id.slice(0, 8)}</option>)}
      </select>
    </label>}
    {older && <p className="text-sm text-gray-600">Showing the 50 most recent runs. Open older work using its full reference below.</p>}
    <details className="rounded-lg border border-gray-200 p-3"><summary className="min-h-11 cursor-pointer py-2 text-sm text-gray-700">Open a run by reference</summary>
      <form onSubmit={event => { event.preventDefault(); selectRun(reference.trim()) }} className="space-y-3">
        <label className="block text-sm text-gray-900">Full run reference<input className={control} required pattern="[a-f0-9]{32}" value={reference} onChange={event => setReference(event.target.value)} /></label>
        <button className={button}>Open saved run</button>
      </form>
    </details>
    {runId && <label className="block text-sm font-medium text-gray-900">Review stage
      <select className={control} value={promptId} onChange={event => { preparedFocus.current = false; setContext(null); setPromptId(event.target.value) }}>
        {prompts.map(prompt => <option key={prompt.id} value={prompt.id}>{prompt.phase === 'before_execution' ? 'Scope before execution' : 'Values after execution'}</option>)}
      </select>
    </label>}
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    {runId && !context && !error && <p role="status" className="text-sm text-gray-600">Loading the saved source and run…</p>}
    {formContext && <div ref={reviewRef} tabIndex={-1} role="region" aria-label="Saved source and learner review" className="min-w-0 outline-offset-4"><DecisionForm key={`${enrollmentId}:${formContext.run_id}:${formContext.prompt.prompt_sha256}`} context={formContext} /></div>}
    {runId && canAct && <PracticalExecution key={`execution:${enrollmentId}:${runId}`} enrollmentId={enrollmentId} moduleId={moduleId} runId={runId}
      onChanged={() => setRefresh(value => value + 1)} onReviewResult={() => {
        const next = prompts.find(prompt => prompt.phase === 'after_execution')
        if (next) { preparedFocus.current = true; setContext(null); setPromptId(next.id); setRefresh(value => value + 1) }
      }} />}
    {canAct && context?.run_state === 'completed' && context.prompt.phase === 'after_execution'
      && <PracticalAssessment key={`request-assessment:${enrollmentId}:${runId}`} enrollmentId={enrollmentId} moduleId={moduleId} runId={runId}
        onOpenFeedback={id => setFeedback(previous => ({ id, revision: (previous?.revision || 0) + 1 }))} />}
    <SavedAutomaticReviews key={`assessments:${enrollmentId}:${moduleId}:${feedback?.revision || 0}`} enrollmentId={enrollmentId} moduleId={moduleId} initialAttemptId={feedback?.id} workNavigationDisabled={loading || !!runError} onOpenWork={review => {
      const next = prompts.find(prompt => prompt.phase === 'after_execution') || prompts[0]
      if (!review.run_id || !next) return
      selectRun(review.run_id); preparedFocus.current = true; setPromptId(next.id)
      setFeedback(null); setRefresh(value => value + 1)
    }} />
  </section>
}

type Draft = { body: PracticalDecisionBody; pending: boolean }
function initialDraft(context: PracticalDecisionContext, key: string): Draft {
  const proposal = context.prompt.phase === 'before_execution' ? context.scope_proposal : null
  try {
    const stored = JSON.parse(sessionStorage.getItem(key) || 'null')
    if (stored && typeof stored.pending === 'boolean' && stored.body?.run_id === context.run_id
      && stored.body.prompt_sha256 === context.prompt.prompt_sha256 && typeof stored.body.reason === 'string'
      && (stored.body.repair_case_sha256 ?? null) === (context.repair_case?.repair_case_sha256 ?? null)
      && typeof stored.body.choice === 'string' && /^[a-f0-9]{32}$/.test(stored.body.request_id)
      && (proposal ? stored.body.proposal_selection?.proposal_sha256 === proposal.proposal_sha256
        && typeof stored.body.proposal_selection?.source_id === 'string' : !stored.body.proposal_selection)
      && Array.isArray(stored.body.value_checks) && stored.body.value_checks.length === context.prompt.required_fields.length
      && stored.body.value_checks.every((check: PracticalValueCheck, index: number) => check.field === context.prompt.required_fields[index]
        && ['supported', 'unsupported', 'unresolved'].includes(check.decision)
        && [check.checked_value, check.source_document_id, check.source_quote, check.reason].every(value => typeof value === 'string'))) return stored
  } catch { /* Saving explains unavailable browser storage before transmission. */ }
  const saved = context.latest_decision?.submission
  return { pending: false, body: saved ? { ...saved, request_id: crypto.randomUUID().replaceAll('-', '') } : {
    request_id: crypto.randomUUID().replaceAll('-', ''), run_id: context.run_id, prompt_sha256: context.prompt.prompt_sha256,
    choice: '', reason: '', value_checks: context.prompt.required_fields.map(field => ({ field, decision: 'unresolved',
      checked_value: '', source_document_id: context.documents[0]?.document_id || '', source_quote: '', reason: '' })),
    ...(proposal ? { proposal_selection: { proposal_sha256: proposal.proposal_sha256, source_id: '' } } : {}),
    ...(context.repair_case ? { repair_case_sha256: context.repair_case.repair_case_sha256 } : {}),
  } }
}

function DecisionForm({ context }: { context: PracticalDecisionContext }) {
  const key = `certification-decision:${context.enrollment_id}:${context.run_id}:${context.prompt.prompt_sha256}`
  const [draft, setDraft] = useState(() => initialDraft(context, key))
  const draftRef = useRef(draft)
  const [saved, setSaved] = useState(context.latest_decision)
  const [busy, setBusy] = useState(false)
  const [checking, setChecking] = useState(false)
  const [canRetry, setCanRetry] = useState(false)
  const sending = useRef(false)
  const [error, setError] = useState('')
  const resultRef = useRef<HTMLDivElement>(null)
  const focusSaved = useRef(false)
  useLayoutEffect(() => {
    if (saved && focusSaved.current && resultRef.current) {
      focusSaved.current = false
      resultRef.current.focus()
    }
  }, [saved])
  function store(next: Draft) {
    sessionStorage.setItem(key, JSON.stringify(next))
    draftRef.current = next; setDraft(next)
  }
  function edit(body: PracticalDecisionBody) {
    const next = { body, pending: false }
    draftRef.current = next; setDraft(next)
    try { store(next); setError('') } catch { setError('This browser could not save your draft. Keep the page open and allow session storage before submitting.') }
  }
  function check(index: number, change: Partial<PracticalValueCheck>) {
    edit({ ...draftRef.current.body, value_checks: draftRef.current.body.value_checks.map((value, position) => position === index ? { ...value, ...change } : value) })
  }
  function verifyReceipt(record: SavedPracticalDecision, body: PracticalDecisionBody) {
    if (record.uuid !== body.request_id || record.enrollment_id !== context.enrollment_id || record.module_id !== context.module_id
      || record.run_id !== context.run_id || record.prompt_id !== context.prompt.id || record.prompt_sha256 !== context.prompt.prompt_sha256
      || (['request_id', 'run_id', 'prompt_sha256', 'choice', 'reason'] as const).some(field => record.submission[field] !== body[field])
      || record.submission.proposal_selection?.proposal_sha256 !== body.proposal_selection?.proposal_sha256
      || record.submission.proposal_selection?.source_id !== body.proposal_selection?.source_id
      || (record.submission.repair_case_sha256 ?? null) !== (body.repair_case_sha256 ?? null)
      || record.submission.value_checks.length !== body.value_checks.length
      || body.value_checks.some((check, index) => (Object.keys(check) as (keyof PracticalValueCheck)[])
        .some(field => record.submission.value_checks[index][field] !== check[field]))) throw new Error('The returned decision does not match this submission')
    return record
  }
  async function submit(retry = false) {
    if (sending.current || (retry && (!canRetry || !context.can_submit || !!context.read_only_reason))) return
    const checkOnly = draftRef.current.pending && !retry
    if (!checkOnly && (!context.can_submit || !!context.read_only_reason)) return
    sending.current = true; setBusy(true); setChecking(checkOnly); setCanRetry(false); setError('')
    let sent = false
    try {
      const pending = { ...draftRef.current, pending: true }
      store(pending)
      let receipt: SavedPracticalDecision | undefined
      if (checkOnly) {
        try { receipt = await getPracticalDecision(pending.body.request_id) }
        catch (failure) {
          if (!(failure instanceof ApiError && failure.status === 404)) throw failure
          const writable = context.can_submit && !context.read_only_reason
          setCanRetry(writable)
          setError(writable
            ? 'No saved decision was found for this reference. Retry the original decision only when you are ready to send these same answers again.'
            : 'No saved decision was found for this reference. This run no longer accepts decision changes. Inspect its saved history before continuing.')
          return
        }
      } else {
        sent = true
        receipt = await submitPracticalDecision(context.enrollment_id, context.module_id, context.prompt.id, pending.body)
      }
      const verified = verifyReceipt(receipt, pending.body)
      focusSaved.current = true
      setSaved(verified)
      store({ pending: false, body: { ...pending.body, request_id: crypto.randomUUID().replaceAll('-', '') } })
    } catch (failure) {
      if (sent && failure instanceof ApiError && failure.status === 422) {
        try {
          store({ pending: false, body: { ...draftRef.current.body, request_id: crypto.randomUUID().replaceAll('-', '') } })
          setError(`${failure.message.replace(/[.!?]$/, '')}. Your decision was not saved. Correct the answers and submit again.`)
          return
        } catch { /* Retain the pending reference if local storage failed. */ }
      }
      setError(draftRef.current.pending
        ? 'We could not confirm the saved decision. Your exact answers and reference are preserved in this tab. Check again before changing them.'
        : 'Your browser could not preserve the submission. Allow session storage before submitting; keep this page open to retain your answers.')
    } finally { sending.current = false; setBusy(false); setChecking(false) }
  }
  const disabled = busy || draft.pending || !context.can_submit
  const proposal = context.scope_proposal
  const repair = context.repair_case
  return <div className="min-w-0 space-y-4">
    {repair && <RepairExample definition={repair.case} />}
    <div className="rounded-lg border border-gray-200 p-4 text-sm text-gray-700">
      <h5 className="font-semibold text-gray-900">{context.artifact.title}</h5>
      <p className="mt-1 break-all">Run reference: {context.run_id}</p>
      <p>Run state: {context.run_state}</p>
      <p className="break-words">Saved lab folder: {context.lab_folder_id || 'Not recorded in this snapshot'}</p>
      <p className="mt-2 font-medium">Saved extraction fields</p>
      <ul className="mt-1 space-y-2">{context.artifact.fields.map((field, index) => <li key={index} className="break-words border-t border-gray-200 pt-2">
        {field.title && <p className="font-medium text-gray-900">{field.title}</p>}
        <p>{field.searchphrase}</p><p>Optional: {field.is_optional ? 'Yes' : 'No'}</p>
        {field.enum_values && <p>Allowed categories: {field.enum_values.length ? field.enum_values.join(', ') : 'None configured'}</p>}
      </li>)}</ul>
    </div>
    {proposal && <div className="space-y-2 rounded-lg border border-gray-300 p-4 text-sm text-gray-800" aria-label="Original scope proposal">
      <h5 className="font-semibold text-gray-900">Assigned task and original proposal</h5>
      <p className="break-words">{proposal.case.task}</p>
      <p className="break-words"><span className="font-medium">Originally proposed source: </span>{proposal.source_options.find(source => source.id === proposal.original_source_id)?.title || proposal.original_source_id}</p>
      <p>Compare the proposed source with the assigned task. Your saved selection records the source you choose before execution.</p>
    </div>}
    {context.documents.map(document => <details key={document.document_id} className="min-w-0 rounded-lg border border-gray-200 p-4">
      <summary className="min-h-11 cursor-pointer break-words py-2 text-sm font-semibold text-gray-900">Saved source: {document.title}</summary>
      <p className="my-2 text-xs text-gray-600">This is the source text captured for this run. Later workspace edits do not change it.</p>
      <pre tabIndex={0} role="region" aria-label={`Saved source text: ${document.title}`} className="max-h-96 overflow-y-auto whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-gray-800 outline-offset-4">{document.text}</pre>
    </details>)}
    {context.result?.entities && <details className="min-w-0 rounded-lg border border-gray-200 p-4" open>
      <summary className="min-h-11 cursor-pointer py-2 text-sm font-semibold text-gray-900">Saved extraction output</summary>
      <pre tabIndex={0} role="region" aria-label="Saved extraction values" className="max-h-96 overflow-y-auto whitespace-pre-wrap break-words text-sm text-gray-800 outline-offset-4">{JSON.stringify(context.result.entities, null, 2)}</pre>
    </details>}
    {!context.can_submit && <p role="status" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">{context.read_only_reason || (context.prompt.phase === 'before_execution'
      ? 'This run has already left preparation. Its earlier scope decisions remain available; a new scope review needs a newly prepared run.'
      : 'Value review becomes available after the saved run completes. Reload saved runs to check its status.')}</p>}
    <form className="space-y-4" onSubmit={event => { event.preventDefault(); void submit() }}>
      <fieldset disabled={disabled} className="min-w-0 space-y-3 rounded-lg border border-gray-200 p-4">
        <legend className="max-w-full px-1 text-sm font-semibold leading-relaxed text-gray-900">{context.prompt.question}</legend>
        {proposal && context.prompt.phase === 'before_execution' && <>
          <label className="block text-sm text-gray-900">Source I would authorize<select className={control} required value={draft.body.proposal_selection?.source_id || ''}
            onChange={event => edit({ ...draft.body, proposal_selection: { proposal_sha256: proposal.proposal_sha256, source_id: event.target.value } })}>
            <option value="">Choose a source</option>
            {proposal.source_options.map(source => <option key={source.id} value={source.id}>{source.title}</option>)}
          </select></label>
          <p className="break-words text-sm text-gray-600">Selected source: {proposal.source_options.find(source => source.id === draft.body.proposal_selection?.source_id)?.title || 'No source selected'}</p>
        </>}
        {Object.entries(context.prompt.choices).map(([id, label]) => <label key={id} className="flex min-h-11 items-start gap-3 rounded-md border border-gray-200 p-3 text-sm text-gray-800 has-checked:border-highlight-text has-checked:bg-highlight/20">
          <input type="radio" required className="mt-1 size-4 shrink-0 accent-highlight-text" name={`decision:${key}`} value={id} checked={draft.body.choice === id} onChange={() => edit({ ...draft.body, choice: id })} /><span className="min-w-0 break-words">{label}</span>
        </label>)}
        <label className="block text-sm text-gray-900">Explain your decision<textarea className={control} rows={3} required minLength={10} maxLength={4000} value={draft.body.reason} onChange={event => edit({ ...draft.body, reason: event.target.value })} /></label>
      </fieldset>
      {draft.body.value_checks.map((value, index) => <fieldset key={value.field} disabled={disabled} className="min-w-0 space-y-3 rounded-lg border border-gray-200 p-4">
        <legend className="px-1 text-sm font-semibold text-gray-900">{value.field}</legend>
        <label className="block text-sm text-gray-900">Value you checked<input className={control} maxLength={4000} value={value.checked_value} onChange={event => check(index, { checked_value: event.target.value })} /></label>
        {repair && <p className="text-sm text-gray-600">Leave the value empty for an absent result. If the absence is supported, cite the source and explain why no value is established.</p>}
        <label className="block text-sm text-gray-900">Source check<select className={control} value={value.decision} onChange={event => check(index, { decision: event.target.value as PracticalValueCheck['decision'] })}>
          <option value="unresolved">Unresolved</option><option value="supported">Supported</option><option value="unsupported">Unsupported</option>
        </select></label>
        <p className="text-sm text-gray-600">{value.decision === 'unresolved' ? 'I cannot verify this value yet.' : value.decision === 'supported' ? 'The assigned source supports this value.' : 'The assigned source does not support this value.'}</p>
        <label className="block text-sm text-gray-900">Assigned source<select className={control} required value={value.source_document_id} onChange={event => check(index, { source_document_id: event.target.value, source_quote: '' })}>
          {context.documents.map(document => <option key={document.document_id} value={document.document_id}>{document.title}</option>)}
        </select></label>
        <p className="break-words text-sm text-gray-600">Selected source: {context.documents.find(document => document.document_id === value.source_document_id)?.title || 'Choose an assigned source'}</p>
        <label className="block text-sm text-gray-900">Exact source passage{value.decision !== 'supported' && ' (if available)'}<textarea className={control} rows={3} maxLength={4000} required={value.decision === 'supported'} value={value.source_quote} onChange={event => check(index, { source_quote: event.target.value })} /></label>
        <label className="block text-sm text-gray-900">What did you establish?<textarea className={control} rows={3} required minLength={10} maxLength={4000} value={value.reason} onChange={event => check(index, { reason: event.target.value })} /></label>
      </fieldset>)}
      {draft.pending && <p role="status" className="break-words rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">Submission awaiting confirmation. Checking reads the saved decision without submitting again.<span className="block break-all">Reference: {draft.body.request_id}</span></p>}
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <p className="text-sm text-gray-600">Drafts stay in this browser tab. Submitted decisions are saved with this course and run.</p>
      <div className="flex flex-wrap gap-2">
        <button type="submit" className={button} disabled={busy || (!draft.pending && (!!context.read_only_reason || !context.can_submit))}>{busy ? checking ? 'Checking saved decision…' : 'Saving decision…' : draft.pending ? 'Check saved decision' : 'Save my decision'}</button>
        {draft.pending && canRetry && context.can_submit && !context.read_only_reason && <button type="button" className="min-h-11 rounded-lg border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-900 disabled:opacity-50" disabled={busy} onClick={() => { void submit(true) }}>Retry original decision</button>}
      </div>
    </form>
    {saved && <div ref={resultRef} tabIndex={-1} className="rounded-lg border border-gray-200 p-4 outline-offset-4" aria-label="Saved practical decision">
      <h5 className="font-semibold text-gray-900">Decision saved</h5>
      <p className="mt-2 text-sm text-gray-700">Your recorded choice: {context.prompt.choices[saved.submission.choice]}</p>
      {saved.submission.proposal_selection && <p className="mt-2 break-words text-sm text-gray-700">Your recorded source: {proposal?.source_options.find(source => source.id === saved.submission.proposal_selection?.source_id)?.title || saved.submission.proposal_selection.source_id}</p>}
      <p className="mt-1 whitespace-pre-wrap break-words text-sm text-gray-700">{saved.submission.reason}</p>
      {saved.submission.value_checks.length > 0 && <details className="mt-3 text-sm text-gray-700"><summary className="min-h-11 cursor-pointer py-2 font-medium">Saved source checks</summary>
        <ul className="space-y-3">{saved.submission.value_checks.map(value => <li key={value.field} className="break-words border-t border-gray-200 pt-3">
          <p className="font-semibold">{value.field}: {value.decision}</p><p>Checked value: {value.checked_value || (value.decision === 'supported' ? 'Empty value (recorded as supported absence)' : 'Empty value; see your source check')}</p>
          {value.source_quote && <blockquote className="my-2 border-l-2 border-gray-300 pl-3 whitespace-pre-wrap">{value.source_quote}</blockquote>}
          <p className="whitespace-pre-wrap">{value.reason}</p>
        </li>)}</ul>
      </details>}
      <p className="mt-2 text-sm text-gray-600">{context.read_only_reason ? 'This saved decision stays with its original course and run.' : 'This records your review. It does not start a run or award a grade. Editing the form creates a separate decision when you save again.'}</p>
      <p className="mt-2 break-all text-xs text-gray-600">Decision reference: {saved.uuid}</p>
    </div>}
  </div>
}


function RepairExample({ definition }: { definition: RepairAssignment }) {
  return (
    <section className="min-w-0 space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-[12px] text-sm text-gray-900 sm:p-4" aria-label="Authored repair example">
      <h5 className="font-semibold">Assigned repair task</h5>
      <p className="break-words">{definition.task}</p>
      <p className="break-words font-medium">{definition.baseline.notice}</p>
      <details>
        <summary className="min-h-11 cursor-pointer py-2 font-semibold">Inspect the original flawed example</summary>
        <ul className="space-y-3">{definition.baseline.fields.map(field => <li key={field.title} className="min-w-0 space-y-1 break-words rounded-lg border border-amber-300 bg-white p-[8px] sm:p-3">
          <h6 className="break-words font-semibold">{field.title}</h6>
          <p className="break-words">Original definition: {field.searchphrase}</p>
          <p>Optional: {field.is_optional ? 'Yes' : 'No'}</p>
          <p className="break-words">Allowed categories: {field.enum_values.length ? field.enum_values.join(', ') : 'None configured'}</p>
          <p className="break-words">Authored flawed value: {definition.baseline.output[field.title] ?? 'No value'}</p>
        </li>)}</ul>
      </details>
    </section>
  )
}
