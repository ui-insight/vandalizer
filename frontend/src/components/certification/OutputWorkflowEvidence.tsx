import { useEffect, useRef, useState } from 'react'
import { getOutputFile } from '../../api/outputWorkflow'
import type { OutputArtifacts, OutputCapture, OutputHandoff, OutputOrigin, OutputRun } from '../../types/outputWorkflow'
import { EvidenceText } from './ConnectedWorkflowEvidence'

export const outputButton = 'min-h-11 min-w-0 max-w-full rounded-lg border border-gray-300 bg-white px-2 py-2 text-left text-sm font-medium text-gray-900 [overflow-wrap:anywhere] disabled:opacity-50 sm:px-4'
export const outputControl = 'mt-1 block min-h-11 w-full min-w-0 max-w-full rounded-lg border border-gray-400 bg-white px-2 py-2 text-sm text-gray-900'
export interface OutputFileLocation { enrollmentId: string; origin: OutputOrigin; reference: string }
export function OutputDownload({ location, kind, index = 0, sha256, filename, children }: {
  location: OutputFileLocation; kind: 'source' | 'file' | 'bundle'; index?: number; sha256: string; filename: string; children: React.ReactNode
}) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const active = useRef(true), sending = useRef(false)
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
  async function download() {
    if (sending.current) return
    sending.current = true; setBusy(true); setError('')
    try {
      const blob = await getOutputFile(location.enrollmentId, location.origin, location.reference, kind, index, sha256)
      if (!active.current) return
      const url = URL.createObjectURL(blob), link = document.createElement('a')
      link.href = url; link.download = filename; link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch { if (active.current) setError('The original file could not be downloaded and verified. Try reading it again; no workflow or handoff was repeated.') }
    finally { sending.current = false; if (active.current) setBusy(false) }
  }
  return <div className="min-w-0 space-y-1"><button type="button" className={outputButton} disabled={busy} onClick={() => { void download() }}>{busy ? 'Checking saved file…' : children}</button>{error && <p role="alert" className="text-sm text-red-800">{error}</p>}</div>
}
export function OutputFiles({ artifacts, location }: { artifacts: OutputArtifacts; location: OutputFileLocation }) {
  return <section aria-label="Actual generated files" className="min-w-0 space-y-3 text-sm">
    <h5 className="text-base font-semibold">Inspect the actual files</h5>
    <p>Download and open each file and every bundle member. The checks below establish file structure and required labels, not source accuracy or visual quality.</p>
    {!artifacts.all_required_files_parseable && <p className="rounded-lg border border-amber-400 bg-amber-50 px-1.5 py-3 sm:p-3">At least one file is invalid or incomplete. Hold release and repair the workflow before generating a new revision.</p>}
    {artifacts.files.map((file, index) => <article key={file.sha256} className="min-w-0 space-y-2 rounded-lg border border-gray-300 px-1.5 py-3 sm:p-3">
      <h6 className="font-semibold">{file.filename}</h6><p>{file.file_type.toUpperCase()} · {file.size_bytes.toLocaleString()} bytes · {file.inspection.parseable_and_fields_present ? 'Structure and required fields found' : 'Repair needed'}</p>
      {file.inspection.issues.length > 0 && <ul className="list-disc space-y-1 pl-4">{file.inspection.issues.map(issue => <li key={issue}>{issue.replaceAll('_', ' ')}</li>)}</ul>}
      <OutputDownload location={location} kind="file" index={index} sha256={file.sha256} filename={file.filename}>Download {file.filename}</OutputDownload>
      <details><summary className="min-h-11 cursor-pointer py-2">Read extracted content from {file.filename}</summary><EvidenceText label={`Extracted content: ${file.filename}`} value={file.inspection.text} /></details>
      <details><summary className="min-h-11 cursor-pointer py-2">File identity for {file.filename}</summary><p className="break-all text-xs">SHA-256: {file.sha256}</p></details>
    </article>)}
    <OutputDownload location={location} kind="bundle" sha256={artifacts.download.sha256} filename={artifacts.download.filename}>Download the actual deliverables bundle</OutputDownload>
    <p>The bundle contains {artifacts.files.map(file => file.filename).join(' and ')}. Check both members after opening it.</p>
  </section>
}
export function OutputCaptureEvidence({ capture }: { capture: OutputCapture }) {
  return <section aria-label="Saved output workflow inputs" className="min-w-0 space-y-3 text-sm">
    <h5 className="text-base font-semibold">{capture.artifact.workflow.name} · workflow version {capture.artifact.workflow.version}</h5>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Inspect saved workflow settings</summary>{capture.artifact.steps.map((item, index) => <div key={item.step.id} className="min-w-0 space-y-2 py-2"><h6 className="font-semibold">{index + 1}. {item.step.name}</h6><EvidenceText label={`Output settings for ${item.step.name}`} value={{ step: item.step.data, tasks: item.tasks.map(task => ({ name: task.name, settings: task.data })) }} /></div>)}</details>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Read the original assigned progress report</summary><EvidenceText label="Original progress report text" value={capture.documents[0].text} /></details>
  </section>
}
const states: Record<OutputRun['state'], string> = { prepared: 'Prepared · not run', executing: 'Generation started · no final receipt', completed: 'Files generated · handoff is separate', failed: 'Generation stopped', uncertain: 'Generation outcome uncertain' }
export function OutputRunEvidence({ run, location }: { run: OutputRun; location?: OutputFileLocation }) {
  const fileLocation: OutputFileLocation = location || { enrollmentId: run.enrollment_id, origin: 'run', reference: run.run_id }
  return <section aria-label="Saved output run" className="min-w-0 space-y-3 text-sm">
    <h5 className="text-base font-semibold">{states[run.state]}</h5><OutputCaptureEvidence capture={run.input_snapshot} />
    <OutputDownload location={fileLocation} kind="source" sha256={run.input_snapshot.case.source_sha256} filename={run.input_snapshot.case.source_filename}>Download the original assigned PDF</OutputDownload>
    <p>Models in this saved plan: {run.model_names.join(', ')}</p>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Inspect all four stages and their saved results</summary>{run.stage_plans.map((stage, index) => {
      const events = run.stage_events.filter(item => item.receipt.stage_index === index)
      const started = events.find(item => item.receipt.kind === 'stage_started'), completed = events.find(item => item.receipt.kind === 'stage_completed')
      return <section key={stage.step_id} className="min-w-0 space-y-2 border-t border-gray-300 py-3">
        <h6 className="font-semibold">{index + 1}. {stage.step_name} · {stage.task_type}</h6>
        <p>{stage.requested_model ? `Model: ${stage.requested_model}. ` : 'No model call in this file stage. '}{stage.receives_previous_stage ? 'Consumes the preceding saved result.' : 'Reads the original assigned report.'} {stage.is_deliverable ? 'Included in the download bundle.' : ''}</p>
        <p>{completed ? completed.receipt.status === 'completed' ? 'Result saved' : 'Stage failed' : started ? 'Started; no result saved' : 'Not started'}</p>
        {started && <details><summary className="min-h-11 cursor-pointer py-2">Read actual input for stage {index + 1}</summary><EvidenceText label={`${stage.step_name} actual input`} value={started.receipt.consumed_context} /></details>}
        {completed && <details><summary className="min-h-11 cursor-pointer py-2">Read actual result for stage {index + 1}</summary><EvidenceText label={`${stage.step_name} actual result`} value={completed.receipt.result?.output} /></details>}
      </section>
    })}</details>
    {run.result?.generated_artifacts && <OutputFiles artifacts={run.result.generated_artifacts} location={fileLocation} />}
    {['failed', 'uncertain', 'executing'].includes(run.state) && <p>Inspect the saved prefix before continuing. Unknown or incomplete generation is not a usable file or confirmed handoff.</p>}
    {run.result?.completion_mode && <p>The receipt was recovered from saved file results. Providers were not rerun.</p>}
  </section>
}
export function OutputHandoffEvidence({ handoff, location }: { handoff: OutputHandoff; location?: OutputFileLocation }) {
  return <section aria-label="Private handoff receipt" className="min-w-0 space-y-3 text-sm">
    <h5 className="text-base font-semibold">{handoff.status === 'delivered' ? 'Private training copy confirmed' : 'Controlled training handoff failed'}</h5>
    <p>{handoff.status === 'delivered' ? 'The approved bytes and confirming receipt were saved together in your learner-only training inbox. This does not confirm external delivery.' : 'This authored first attempt was rejected before any destination copy. The generated files are preserved. Retry only this handoff after checking the original failure and current approval.'}</p>
    <p>Destination: your private training inbox. Audience: you alone. Scope: the exact approved generated files.</p>
    {handoff.previous_failed_receipt && <p>Original failed handoff: <span className="break-all">{handoff.previous_failed_receipt.uuid}</span>. Generation was preserved.</p>}
    {handoff.destination_copy && <OutputFiles artifacts={handoff.destination_copy} location={location || { enrollmentId: handoff.enrollment_id, origin: 'handoff', reference: handoff.uuid }} />}
    <details><summary className="min-h-11 cursor-pointer py-2">Read this handoff’s exact identity</summary><EvidenceText label="Private handoff identity" value={{ request: handoff.submission, receipt_sha256: handoff.handoff_sha256, status: handoff.status, destination_written: handoff.destination_written, external_delivery: handoff.external_delivery }} /></details>
  </section>
}
