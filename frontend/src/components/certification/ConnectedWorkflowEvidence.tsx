import type { ConnectedCapture, ConnectedRun } from '../../types/connectedWorkflow'

export const connectedButton = 'min-h-11 min-w-0 max-w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-left text-sm font-medium text-gray-900 [overflow-wrap:anywhere] disabled:opacity-50'
export const connectedControl = 'mt-1 block min-h-11 w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900'
const inputLabels: Record<string, string> = { workflow_documents: 'Workflow Documents', step_input: 'Step Input', select_document: 'Selected document' }
const stateLabels: Record<ConnectedRun['state'], string> = { prepared: 'Prepared · not run', executing: 'Run started · no final receipt', completed: 'Run completed', failed: 'Run stopped', uncertain: 'Run outcome uncertain' }
function inputText(context: Record<string, unknown> | undefined) {
  if (context?.kind === 'combined_context') return context.value
  if (context?.kind === 'extraction_documents' && Array.isArray(context.documents)) {
    return context.documents.map(document => typeof document?.text === 'string' ? document.text : JSON.stringify(document)).join('\n\n')
  }
  return context
}
export function EvidenceText({ label, value }: { label: string; value: unknown }) {
  return <pre tabIndex={0} role="region" aria-label={label} className="max-h-96 min-w-0 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-gray-50 p-2 font-sans text-sm text-gray-900 [overflow-wrap:anywhere]">{typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</pre>
}
export function ConnectedCaptureEvidence({ capture }: { capture: ConnectedCapture }) {
  return <section aria-label="Saved connected inputs" className="min-w-0 space-y-3 text-sm text-gray-900">
    <h5 className="text-base font-semibold">{capture.artifact.workflow.name} · workflow version {capture.artifact.workflow.version}</h5>
    <p>These are the original saved inputs. Later edits in your workspace do not replace them.</p>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Inspect captured configuration</summary>
      {capture.artifact.steps.map((item, index) => <div className="min-w-0 space-y-2 py-2" key={item.step.id}>
        <h6 className="font-semibold">{index + 1}. {item.step.name}</h6>
        <EvidenceText label={`Saved configuration for ${item.step.name}`} value={{ step: item.step.data, tasks: item.tasks.map(task => ({ name: task.name, settings: task.data })) }} />
      </div>)}
      {Object.keys(capture.artifact.referenced_extraction_sets).length > 0 && <EvidenceText label="Captured extraction definitions" value={capture.artifact.referenced_extraction_sets} />}
    </details>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Read the saved assigned source</summary>
      {capture.documents.map(item => <div key={item.document_id} className="min-w-0 space-y-2"><p>{item.assigned_filename}</p><EvidenceText label="Original assigned source text" value={item.text} /></div>)}
    </details>
  </section>
}
export function ConnectedRunEvidence({ run }: { run: ConnectedRun }) {
  return <section aria-label="Saved connected run" className="min-w-0 space-y-3 rounded-lg border border-gray-200 p-2 text-sm text-gray-900 sm:p-4">
    <h5 className="text-base font-semibold">{run.result?.reason === 'controlled_training_rejection_before_reasoning_provider' ? 'Disclosed training stop · original work preserved' : stateLabels[run.state]}</h5>
    {run.execution_purpose === 'controlled_failure_rehearsal' && <p className="rounded-lg border border-amber-300 bg-amber-50 p-2">{run.input_snapshot.case.controlled_failure_practice?.notice}</p>}
    <ConnectedCaptureEvidence capture={run.input_snapshot} />
    <p><strong>Models: </strong>{run.model_names.join(', ')}</p>
    <ol className="space-y-3">{run.stage_plans.map((stage, index) => {
      const start = run.stage_events.find(item => item.receipt.stage_index === index && item.receipt.kind === 'stage_started')
      const result = run.stage_events.find(item => item.receipt.stage_index === index && item.receipt.kind === 'stage_completed')
      return <li key={stage.step_id} className="min-w-0 border-t border-gray-200 pt-2">
        <h6 className="font-semibold">{index + 1}. {stage.step_name}</h6>
        <p>Input: {stage.effective_input_sources.map(value => inputLabels[value] || value).join(', ')}</p>
        <p>{result ? result.receipt.status === 'completed' ? 'Result saved' : 'Stage stopped' : start ? 'Started · no saved result' : 'Not started'}</p>
        {start && <details><summary className="min-h-11 cursor-pointer py-2">Inspect actual input for stage {index + 1}</summary><EvidenceText label={`Actual input for stage ${index + 1}`} value={inputText(start.receipt.consumed_context)} />
          <details><summary className="min-h-11 cursor-pointer py-2">Input evidence details</summary><EvidenceText label={`Input evidence details for stage ${index + 1}`} value={start.receipt.consumed_context} /></details>
        </details>}
        {result && <details><summary className="min-h-11 cursor-pointer py-2">Inspect actual result for stage {index + 1}</summary><EvidenceText label={`Actual result for stage ${index + 1}`} value={result.receipt.result?.formatted_output ?? result.receipt.result?.output ?? result.receipt.result?.error ?? result.receipt.result} />
          <details><summary className="min-h-11 cursor-pointer py-2">Result evidence and source details</summary><EvidenceText label={`Result evidence details for stage ${index + 1}`} value={result.receipt.result} /></details>
        </details>}
      </li>
    })}</ol>
    {run.scope_decision && <details><summary className="min-h-11 cursor-pointer py-2">Saved scope choice: {run.scope_decision.submission.choice === 'approve' ? 'Approved' : 'Held'}</summary><EvidenceText label="Original scope explanation" value={run.scope_decision.submission.reason} /></details>}
    {run.state === 'completed' && <><h6 className="font-semibold">Actual final output</h6><EvidenceText label="Saved final output" value={run.result?.final_output} /></>}
    {run.result?.completion_mode && <p>The final receipt was recovered from saved stage results. The original finish time is unavailable; no provider was rerun.</p>}
    {['failed', 'uncertain', 'executing'].includes(run.state) && <p>The saved stages remain available for inspection. This screen does not restart incomplete stages. A new run needs a new plan and your approval.</p>}
    <details><summary className="min-h-11 cursor-pointer py-2">Run and capture references</summary><p className="break-all">Run: {run.run_id}</p><p className="break-all">Capture: {run.input_snapshot_id}</p></details>
    <p>Saved execution is evidence for assessment. It does not award credit or certify source accuracy.</p>
  </section>
}
