import type { BudgetCapture, BudgetRun } from '../../types/budgetWorkflow'
import { BudgetCalculationEvidence } from './BudgetCalculations'
import { EvidenceText } from './ConnectedWorkflowEvidence'

export function BudgetCaptureEvidence({ capture }: { capture: BudgetCapture }) {
  return <section aria-label="Saved budget workflow inputs" className="min-w-0 space-y-3 text-sm text-gray-900">
    <h5 className="text-base font-semibold">{capture.artifact.workflow.name} · workflow version {capture.artifact.workflow.version}</h5>
    <p>Original method decision: {capture.method_choice}</p>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Inspect saved workflow settings</summary>
      {capture.artifact.steps.map((item, index) => <div key={item.step.id} className="min-w-0 space-y-2 py-2"><h6 className="font-semibold">{index + 1}. {item.step.name}</h6><EvidenceText label={`Budget settings for ${item.step.name}`} value={{ step: item.step.data, tasks: item.tasks.map(task => ({ name: task.name, settings: task.data })) }} /></div>)}
    </details>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Inspect the exact saved calculations and source</summary><BudgetCalculationEvidence calculation={capture.calculation} /></details>
  </section>
}
const states: Record<BudgetRun['state'], string> = { prepared: 'Prepared · not run', executing: 'Run started · no final receipt', completed: 'Run completed', failed: 'Run stopped', uncertain: 'Run outcome uncertain' }
export function BudgetRunEvidence({ run }: { run: BudgetRun }) {
  return <section aria-label="Saved budget run" className="min-w-0 space-y-3 text-sm text-gray-900">
    <h5 className="text-base font-semibold">{states[run.state]}</h5><BudgetCaptureEvidence capture={run.input_snapshot} />
    <p>Models in this saved plan: {run.model_names.join(', ')}</p>
    {run.stage_plans.map((stage, index) => <section key={stage.step_id} className="min-w-0 space-y-2 rounded-lg border border-gray-200 p-3">
      <h6 className="font-semibold">{index + 1}. {stage.step_name}</h6><p>{stage.waits_for_previous_stage ? 'Waits for every preceding review result.' : stage.tasks.length > 1 ? 'Independent reviews share the source inputs; sibling results are unavailable until the step finishes.' : 'Source review runs before the memo.'}</p>
      {stage.tasks.map((task, taskIndex) => { const events = run.task_events.filter(item => item.receipt.stage_index === index && item.receipt.task_index === taskIndex); const started = events.find(item => item.receipt.kind === 'task_started'); const completed = events.find(item => item.receipt.kind === 'task_completed'); const failed = events.find(item => item.receipt.kind === 'task_failed'); return <div key={task.task_id} className="min-w-0 space-y-2 border-t border-gray-200 py-2">
        <p className="font-semibold">Task {taskIndex + 1}: {task.task_type} · {completed ? 'Result saved' : failed ? 'Stopped' : started ? 'Started; no result saved' : 'Not started'}</p>
        <p>{task.model} · Inputs: {task.effective_input_sources.map(source => source === 'step_input' ? 'Previous step output' : source === 'workflow_documents' ? 'Assigned budget and saved calculations' : 'Selected document').join(', ')}</p>
        {failed && <p>{failed.receipt.failure_kind === 'required_task_result_missing'
          ? 'This task did not return a usable result. A dependent memo cannot treat it as completed.'
          : failed.receipt.failure_kind === 'task_execution_unavailable'
            ? 'This model operation was unavailable or failed. No completed result was saved for this task.'
            : 'This task stopped without a completed result. Inspect the saved evidence before deciding what to do next.'}</p>}
        {started && <details><summary className="min-h-11 cursor-pointer py-2">Read actual input for task {taskIndex + 1}</summary><EvidenceText label={`${stage.step_name} task ${taskIndex + 1} actual input`} value={started.receipt.consumed_context} /></details>}
        {completed && <details><summary className="min-h-11 cursor-pointer py-2">Read actual result for task {taskIndex + 1}</summary><EvidenceText label={`${stage.step_name} task ${taskIndex + 1} actual result`} value={completed.receipt.result?.output} /></details>}
      </div> })}
    </section>)}
    {run.result?.final_output && <><h6 className="font-semibold">Saved internal memo</h6><EvidenceText label="Final budget memo" value={run.result.final_output} /></>}
    {run.state === 'failed' || run.state === 'uncertain' || run.state === 'executing' ? <p>Inspect the saved task receipts before any further action. Completed work stays preserved. An incomplete or unknown result is not a completed memo.</p> : null}
    {run.state === 'failed' && <p>To revise this work, open the saved workflow in the editor and correct the stopped task or select an available model. Then save a new workflow and method decision using your calculation record, prepare the new plan and inspect it before approving another run. The original stopped run and its completed results stay in history; this does not resume or reuse its task outputs automatically.</p>}
    {(run.state === 'uncertain' || run.state === 'executing') && <p>Open this saved run again to check its recorded state. If finalization is offered, it uses the saved task results without running the model again. Otherwise keep the unresolved result visible; do not start a replacement run just to clear this status.</p>}
    {run.result?.completion_mode && <p>The final receipt was recovered from saved task results. Providers were not rerun.</p>}
  </section>
}
