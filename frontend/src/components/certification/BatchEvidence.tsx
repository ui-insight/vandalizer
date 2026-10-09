import { useEffect, useRef, useState } from 'react'
import { getBatchSource } from '../../api/batchAssessment'
import type { BatchCapture, BatchOrigin, BatchRun } from '../../types/batchAssessment'
import { EvidenceText } from './ConnectedWorkflowEvidence'
export { outputButton as batchButton, outputControl as batchControl } from './OutputWorkflowEvidence'
import { outputButton as button } from './OutputWorkflowEvidence'
export interface BatchLocation { enrollmentId: string; origin: BatchOrigin; reference: string }

function SourceDownload({ capture, source, location }: { capture: BatchCapture; source: BatchCapture['documents'][number]; location: BatchLocation }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const active = useRef(true), sending = useRef(false)
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
  async function download() {
    if (sending.current) return
    sending.current = true; setBusy(true); setError('')
    try {
      const blob = await getBatchSource(capture.enrollment_id, location.origin, location.reference, source.source_id, source.source_sha256)
      if (!active.current) return
      const url = URL.createObjectURL(blob), link = document.createElement('a')
      link.href = url; link.download = source.assigned_filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch { if (active.current) setError('The original PDF could not be downloaded and verified. Try reading it again.') }
    finally { sending.current = false; if (active.current) setBusy(false) }
  }
  return <div><button type="button" className={button} disabled={busy} onClick={() => { void download() }}>{busy ? 'Checking original PDF…' : `Download original ${source.source_id.toUpperCase()} PDF`}</button>{error && <p role="alert" className="text-sm text-red-800">{error}</p>}</div>
}
export function BatchCaptureEvidence({ capture, location }: { capture: BatchCapture; location?: BatchLocation }) {
  return <section aria-label="Saved batch inputs" className="min-w-0 space-y-3 text-sm">
    <h5 className="text-base font-semibold">{capture.artifact.title}</h5>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Inspect captured field instructions</summary>{capture.artifact.fields.map(field => <div key={field.id} className="space-y-1 py-2"><h6 className="font-semibold">{field.title}</h6><p>{field.searchphrase}</p><p>{field.is_optional ? 'Optional field' : 'Required field'}</p></div>)}</details>
    {capture.documents.map(source => <section key={source.source_id} className="min-w-0 space-y-2">
      <h6 className="font-semibold">{source.source_id.toUpperCase()} · complete original source</h6>
      <SourceDownload capture={capture} source={source} location={location || { enrollmentId: capture.enrollment_id, origin: 'capture', reference: capture.uuid }} />
      <details><summary className="min-h-11 cursor-pointer py-2">Read {source.source_id.toUpperCase()} source pages</summary>{source.pages.map((page, i) => <div key={i}><p className="py-2 font-semibold">Page {i + 1}</p><EvidenceText label={`${source.source_id.toUpperCase()} page ${i + 1}`} value={page} /></div>)}</details>
    </section>)}
  </section>
}
const states = { prepared: 'Prepared · not run', executing: 'Started · no final receipt', completed: 'Terminal inventory saved', failed: 'Execution stopped', uncertain: 'Execution outcome uncertain' }
export const batchPhaseLabel = { pilot: 'Two-document pilot', batch: 'Three-document batch', retry: 'Targeted item retry' }
export function BatchRunEvidence({ run, location, nested = false }: { run: BatchRun; location?: BatchLocation; nested?: boolean }) {
  const sourceLocation = location || { enrollmentId: run.enrollment_id, origin: 'run' as const, reference: run.run_id }
  const checks = run.result?.checks
  return <section aria-label={nested ? 'Preserved batch ancestry' : 'Saved batch run'} className="min-w-0 space-y-3 text-sm">
    <h5 className="text-base font-semibold">{batchPhaseLabel[run.phase]} · {states[run.state]}</h5>
    <p>Models: {run.model_names.join(', ')}. This action includes {run.source_ids.map(s => s.replace('_', ' ')).join(', ')}.</p>
    {!nested && <BatchCaptureEvidence capture={run.input_snapshot} location={sourceLocation} />}
    {run.scope_decision && <p>Saved scope choice: <strong>{run.scope_decision.submission.choice}</strong>. {run.scope_decision.submission.reason}</p>}
    {checks && <section aria-label="Batch item inventory" className="space-y-3">
      <h6 className="font-semibold">{checks.all_values_source_supported ? 'Every selected item has source-supported values' : checks.all_items_completed ? 'All selected items finished · inspect source quality' : 'Mixed terminal inventory · failed items remain visible'}</h6>
      <p>Terminal coverage: {checks.terminal_coverage_complete ? 'complete' : 'incomplete'}. Successful item coverage: {checks.all_items_completed ? 'complete' : 'incomplete'}. Total measured item time: {checks.elapsed_ms} ms. Token usage and price: unknown.</p>
      {checks.items.map(item => {
        const actual = run.result?.item_results?.find(r => r.source_id === item.source_id)
        return <article key={item.source_id} className="min-w-0 space-y-2 rounded-lg border border-gray-300 px-[6px] py-3 sm:p-3">
          <h6 className="font-semibold">{item.source_id.replace('_', ' ')} · {item.status === 'completed' ? 'Extraction completed' : 'Failed item'}</h6>
          <p>{actual?.reason === 'controlled_training_rejection_before_dispatch' ? 'Disclosed training rejection before model dispatch. This was not a provider outage.' : actual?.reason === 'extraction_unavailable' ? 'Extraction was attempted but no usable result was returned.' : item.source_supported ? 'All five values match the original source.' : 'Inspect missing or mismatched values before claiming usable output.'}</p>
          <details><summary className="min-h-11 cursor-pointer py-2">Inspect {item.source_id.replace('_', ' ')} values and identity</summary>
            {item.fields.map(field => <div key={field.field} className="space-y-1 border-t border-gray-200 py-2"><p className="font-semibold">{field.field}</p><p>Actual: {field.output_comparable ? String(field.actual_value) : 'Unavailable or malformed'}</p><p>Source check: {field.output_comparable ? field.matches_source ? 'Supported' : 'Mismatch' : 'Unavailable'}</p></div>)}
            <p className="break-all">Assigned document: {item.document_id}</p><p className="break-all">Original batch: {item.batch_id}</p><p className="break-all">Item receipt SHA-256: {item.receipt_sha256}</p>
          </details>
        </article>
      })}
    </section>}
    {['failed', 'uncertain', 'executing'].includes(run.state) && <p>This state does not establish a complete item inventory. Read the original receipt before considering further work; opening it never repeats extraction.</p>}
    <details><summary className="min-h-11 cursor-pointer py-2">Inspect actual saved item receipts</summary><EvidenceText label="Batch item receipts" value={run.item_events} /></details>
    {run.parent_run && <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Inspect preserved {run.parent_run.phase === 'pilot' ? 'pilot before scaling' : 'original batch'}</summary><BatchRunEvidence run={run.parent_run} location={sourceLocation} nested /></details>}
    {run.previous_retry && <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Inspect the previous failed retry</summary><BatchRunEvidence run={run.previous_retry} location={sourceLocation} nested /></details>}
    <details><summary className="min-h-11 cursor-pointer py-2">Saved run reference</summary><p className="break-all">{run.run_id}</p></details>
  </section>
}
