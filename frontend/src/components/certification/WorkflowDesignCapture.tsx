import { CourseRequestStatus, type CourseRequestPhase } from './CourseRequestStatus'
import { useEffect, useRef, useState } from 'react'
import { captureWorkflowDesign, getWorkflowDesignCapture } from '../../api/certification'
import { ApiError } from '../../api/client'
import { CourseEditorLink } from './CourseEditorLink'
import type { SavedWorkflowDesignCapture, WorkflowDesignCaptureBody, WorkflowDesignList } from '../../types/certification'

export const designButton = 'min-h-11 min-w-0 max-w-full rounded-lg border border-gray-300 bg-white px-2 py-2 text-left text-sm font-medium text-gray-900 [overflow-wrap:anywhere] disabled:opacity-50'
export const designControl = 'mt-1 block min-h-11 w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900'
const id = (value: string) => /^[a-f0-9]{32}$/.test(value)
export function validCapture(value: SavedWorkflowDesignCapture, listing: WorkflowDesignList, reference: string, expected?: WorkflowDesignCaptureBody) {
  return value.uuid === reference && id(reference) && value.enrollment_id === listing.enrollment_id && value.module_id === 'workflow_design'
    && value.course_version === listing.course_version && value.manifest_sha256 === listing.manifest_sha256
    && value.case.case_sha256 === listing.case.case_sha256 && value.case.module_id === 'workflow_design'
    && value.request.request_id === reference && value.request.case_sha256 === listing.case.case_sha256
    && value.request.consent === 'capture_saved_workflow_design' && value.request.workflow_id === value.artifact_id
    && value.artifact.workflow.id === value.artifact_id && /^[a-f0-9]{64}$/.test(value.input_snapshot_sha256)
    && /^[a-f0-9]{64}$/.test(value.artifact_sha256) && value.credit_awarded === false && value.module_completion_eligible === false
    && value.execution_status === 'not_started' && value.handoff.kind === value.request.handoff
    && (!expected || (value.request.workflow_id === expected.workflow_id && value.request.handoff === expected.handoff
      && value.request.process_submission_id === expected.process_submission_id))
}

export function WorkflowDesignCapture({ listing, captured, onCaptured, onPendingChange }: {
  listing: WorkflowDesignList; captured: SavedWorkflowDesignCapture | null; onCaptured: (value: SavedWorkflowDesignCapture) => void; onPendingChange: (value: boolean) => void
}) {
  const [phase, setPhase] = useState<CourseRequestPhase>('checking')
  const key = `certification-workflow-capture:${listing.enrollment_id}:${listing.case.case_sha256}`
  const selectedKey = `${key}:selected`
  const [workflow, setWorkflow] = useState(''), [map, setMap] = useState('supplied_example')
  const [pending, setPending] = useState<WorkflowDesignCaptureBody | null>(null)
  const [canFinish, setCanFinish] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(''), [blocked, setBlocked] = useState(false)
  const sending = useRef(false), sequence = useRef(0)
  useEffect(() => {
    let active = true
    const counter = sequence
    try {
      const value = JSON.parse(sessionStorage.getItem(key) || 'null') as WorkflowDesignCaptureBody | null
      if (value) {
        if (!id(value.request_id) || !/^[a-f0-9]{24}$/.test(value.workflow_id) || value.case_sha256 !== listing.case.case_sha256
          || value.consent !== 'capture_saved_workflow_design' || !['supplied_example', 'owned_saved_process_submission'].includes(value.handoff)
          || (value.handoff === 'supplied_example' ? value.process_submission_id !== null : !id(value.process_submission_id || ''))) throw new Error('Invalid request')
        setPending(value); onPendingChange(true); setWorkflow(value.workflow_id); setMap(value.process_submission_id || 'supplied_example')
      } else {
        const previous = sessionStorage.getItem(selectedKey)
        if (previous && !captured) {
          setPhase('checking'); setBusy(true)
          void getWorkflowDesignCapture(listing.enrollment_id, previous).then(saved => {
            if (!active) return
            if (!validCapture(saved, listing, previous)) throw new Error('Different capture')
            onCaptured(saved)
          }).catch(() => { if (active) setError('The earlier capture could not be restored. Saved approvals remain in history. Choose and capture a revision before making a new approval.') })
            .finally(() => { if (active) setBusy(false) })
        }
      }
    } catch { setBlocked(true); onPendingChange(true); setError('This tab could not restore its capture request. Reload before capturing if an earlier request was interrupted.') }
    return () => { active = false; counter.current++ }
    // Changes to approval/history state do not reload or replace this capture.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, selectedKey, listing.enrollment_id, listing.case.case_sha256])

  async function act(check = false) {
    if (sending.current || blocked || (pending && !check && !canFinish)) return
    sending.current = true; const token = ++sequence.current
    setPhase(check ? 'checking' : 'sending'); setBusy(true); setError(''); setCanFinish(false)
    let sent = false
    try {
      const body: WorkflowDesignCaptureBody = pending || { request_id: crypto.randomUUID().replaceAll('-', ''), workflow_id: workflow,
        case_sha256: listing.case.case_sha256, handoff: map === 'supplied_example' ? 'supplied_example' : 'owned_saved_process_submission',
        process_submission_id: map === 'supplied_example' ? null : map, consent: 'capture_saved_workflow_design' }
      if (!check) { sessionStorage.setItem(key, JSON.stringify(body)); setPending(body); onPendingChange(true); sent = true }
      const saved = await (check ? getWorkflowDesignCapture(listing.enrollment_id, body.request_id) : captureWorkflowDesign(listing.enrollment_id, body))
      if (!validCapture(saved, listing, body.request_id, body)) throw new Error('Different capture')
      if (token !== sequence.current) return
      sessionStorage.setItem(selectedKey, saved.uuid); sessionStorage.removeItem(key)
      setPending(null); onPendingChange(false); onCaptured(saved)
    } catch (failure) {
      if (token !== sequence.current) return
      if (check && failure instanceof ApiError && failure.status === 404) { setCanFinish(true); setError('No capture is saved for this reference. Finish the same capture request to preserve your selection.') }
      else if (sent && failure instanceof ApiError && failure.status === 422) { sessionStorage.removeItem(key); setPending(null); onPendingChange(false); setError('The capture was not saved. Check the workflow and map selection.') }
      else if (!check && !sent) setError('This tab could not preserve the request; no capture request was sent. Allow session storage before trying again.')
      else setError('We could not confirm the capture. Check its saved state before sending again. Your earlier approvals are preserved.')
    } finally { sending.current = false; if (token === sequence.current) setBusy(false) }
  }
  return <section aria-label="Choose workflow revision" className="min-w-0 space-y-3 rounded-lg border border-gray-200 p-2 sm:p-4">
    <h5 className="text-base font-semibold text-gray-900">Capture a saved workflow revision</h5>
    <p className="text-sm text-gray-700">Create or refine your workflow in chat or the editor, then return here. Capture preserves its current configuration and the map you choose; it does not run anything. Inspect the captured settings before approving them.</p>
    <form className="space-y-3" onSubmit={event => { event.preventDefault(); void act() }}>
      <label className="block text-sm text-gray-900">Saved workflow<select className={designControl} required value={workflow} onChange={event => setWorkflow(event.target.value)} disabled={busy || !!pending || blocked}>
        <option value="">Choose your workflow</option>{listing.workflows.map(item => <option value={item.workflow_id} key={item.workflow_id}>{item.name} · revision {item.version}</option>)}
        {listing.older_workflows_available && workflow && !listing.workflows.some(item => item.workflow_id === workflow) && <option value={workflow}>Older workflow · {workflow}</option>}
      </select></label>
      {listing.workflows.filter(item => item.workflow_id === workflow).map(item => <CourseEditorLink key={item.workflow_id} kind="workflow" artifactId={item.workflow_id} title={item.name} disabled={busy || !!pending || blocked} />)}
      {!listing.workflows.length && <p className="text-sm text-gray-700">No owned workflows are available. Save one in your workspace, then refresh the choices.</p>}
      {listing.older_workflows_available && <label className="block text-sm text-gray-900">Older workflow reference<input className={designControl} pattern="[a-f0-9]{24}" value={workflow} onChange={event => setWorkflow(event.target.value)} disabled={busy || !!pending || blocked} /></label>}
      <label className="block text-sm text-gray-900">Starting process map<select className={designControl} value={map} onChange={event => setMap(event.target.value)} disabled={busy || !!pending || blocked}>
        <option value="supplied_example">Use the supplied example</option>{listing.process_choices.map(item => <option key={item.submission_id} value={item.submission_id}>My saved map · {item.submission_id.slice(0, 8)}</option>)}
        {listing.older_process_choices_available && map !== 'supplied_example' && !listing.process_choices.some(item => item.submission_id === map) && <option value={map}>Older saved map · {map}</option>}
      </select></label>
      {listing.older_process_choices_available && <label className="block text-sm text-gray-900">Older process map reference<input className={designControl} pattern="[a-f0-9]{32}" value={map === 'supplied_example' ? '' : map} onChange={event => setMap(event.target.value || 'supplied_example')} disabled={busy || !!pending || blocked} /></label>}
      {!pending && <button className={designButton} disabled={busy || blocked || !workflow}>Capture selected revision</button>}
    </form>
    {pending && <><p className="text-sm text-gray-700">Your original capture request is preserved. Checking its state does not execute the workflow.</p>
      <button className={designButton} disabled={busy} onClick={() => { void act(true) }}>Check saved capture</button>
      {canFinish && <button className={designButton} disabled={busy || blocked} onClick={() => { void act() }}>Finish original capture request</button>}</>}
    <CourseRequestStatus phase={busy ? phase : null} action="capture" />
    {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
  </section>
}

export function WorkflowSnapshot({ value }: { value: SavedWorkflowDesignCapture | Omit<SavedWorkflowDesignCapture, 'input_snapshot_sha256'> }) {
  return <section aria-label="Captured workflow configuration" className="min-w-0 space-y-3 rounded-lg border border-gray-200 p-2 text-sm text-gray-900 sm:p-4">
    <h5 className="font-semibold">{value.artifact.workflow.name} · captured revision {value.artifact.workflow.version}</h5>
    <p>This is the saved configuration for this attempt. It is not a completed run or proof that its connections are correct.</p>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Inspect the original process map</summary>
      <pre tabIndex={0} role="region" aria-label="Original process map" className="max-h-96 overflow-auto whitespace-pre-wrap break-words font-sans">{value.handoff.kind === 'supplied_example'
        ? JSON.stringify(value.handoff.supplied_map, null, 2) : JSON.stringify(value.handoff.original_submission?.submission.answers, null, 2)}</pre>
    </details>
    <ol className="space-y-3">{value.artifact.steps.map((item, index) => <li key={item.step.id} className="min-w-0">
      <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">{index + 1}. {item.step.name}{item.step.is_output ? ' · output' : ''}</summary>
        <pre tabIndex={0} role="region" aria-label={`Captured settings for ${item.step.name}`} className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-gray-50 p-2 text-xs">{JSON.stringify({ step: item.step.data, tasks: item.tasks }, null, 2)}</pre>
      </details>
    </li>)}</ol>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Input, output and referenced extraction settings</summary>
      <pre tabIndex={0} role="region" aria-label="Captured workflow settings" className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-gray-50 p-2 text-xs">{JSON.stringify({ input: value.artifact.workflow.input_config, output: value.artifact.workflow.output_config,
        resources: value.artifact.workflow.resource_config, overrides: value.artifact.workflow.config_override, extractions: value.artifact.referenced_extraction_sets }, null, 2)}</pre>
    </details>
    <details><summary className="min-h-11 cursor-pointer py-2">Capture reference</summary><p className="break-all">{value.uuid}</p></details>
  </section>
}
