import { useEffect, useRef, useState } from 'react'
import { getValidationSource } from '../../api/validationSuite'
import type { ValidationCapture, ValidationOrigin, ValidationRun, ValidationSuiteRecord } from '../../types/validationSuite'
import { EvidenceText } from './ConnectedWorkflowEvidence'
export { outputButton as validationButton, outputControl as validationControl } from './OutputWorkflowEvidence'
import { outputButton as button } from './OutputWorkflowEvidence'
export interface ValidationLocation { enrollmentId: string; origin: ValidationOrigin; reference: string }

function SourceDownload({ capture, source, location }: { capture: ValidationCapture; source: ValidationCapture['documents'][number]; location: ValidationLocation }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const active = useRef(true), sending = useRef(false)
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
  async function download() {
    if (sending.current) return
    sending.current = true; setBusy(true); setError('')
    try {
      const blob = await getValidationSource(capture.enrollment_id, location.origin, location.reference, source.source_id, source.source_sha256)
      if (!active.current) return
      const url = URL.createObjectURL(blob), link = document.createElement('a')
      link.href = url; link.download = source.assigned_filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch { if (active.current) setError('The original PDF could not be downloaded and verified. Try reading it again.') }
    finally { sending.current = false; if (active.current) setBusy(false) }
  }
  return <div><button type="button" className={button} disabled={busy} onClick={() => { void download() }}>{busy ? 'Checking original PDF…' : `Download original ${source.source_id.toUpperCase()} PDF`}</button>{error && <p role="alert" className="text-sm text-red-800">{error}</p>}</div>
}
export function ValidationCaptureEvidence({ capture, location }: { capture: ValidationCapture; location?: ValidationLocation }) {
  return <section aria-label="Saved validation inputs" className="min-w-0 space-y-3 text-sm">
    <h5 className="text-base font-semibold">{capture.artifact.title}</h5>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Inspect captured field instructions</summary>{capture.artifact.fields.map(field => <div key={field.id} className="space-y-1 py-2"><h6 className="font-semibold">{field.title}</h6><p>{field.searchphrase}</p><p>{field.is_optional ? 'Optional field · explicit absence still tested' : 'Required field'}</p></div>)}</details>
    {capture.documents.map(source => <section key={source.source_id} className="min-w-0 space-y-2">
      <h6 className="font-semibold">{source.source_id.toUpperCase()} · complete original source</h6>
      <SourceDownload capture={capture} source={source} location={location || { enrollmentId: capture.enrollment_id, origin: 'capture', reference: capture.uuid }} />
      <details><summary className="min-h-11 cursor-pointer py-2">Read {source.source_id.toUpperCase()} source pages</summary>{source.pages.map((page, i) => <div key={i}><p className="py-2 font-semibold">Page {i + 1}</p><EvidenceText label={`${source.source_id.toUpperCase()} page ${i + 1}`} value={page} /></div>)}</details>
    </section>)}
  </section>
}
export function ValidationSuiteEvidence({ suite }: { suite: ValidationSuiteRecord }) {
  return <details className="min-w-0 text-sm"><summary className="min-h-11 cursor-pointer py-2 font-semibold">Read all six saved expectations and source reasons</summary>
    <p className="py-2">{suite.submission.suite_design}</p>
    {suite.submission.expectations.map(e => <article key={`${e.source_id}:${e.field}`} className="min-w-0 space-y-2 border-t border-gray-300 py-3"><h6 className="font-semibold">{e.source_id.toUpperCase()} · {e.field}</h6><p>Expected: {e.expected_kind === 'explicit_absence' ? 'Explicit absence' : e.expected_value}</p><p>{e.source_reason}</p>{e.source_references.map((a, i) => <blockquote key={i} className="border-l-2 border-gray-400 pl-2">Page {a.page}: {a.quote}</blockquote>)}</article>)}
  </details>
}
const states = { prepared: 'Prepared · not run', executing: 'Started · no final receipt', completed: 'Complete suite result saved', failed: 'Execution stopped', uncertain: 'Execution outcome uncertain' }
export function ValidationRunEvidence({ run, location, original = false }: { run: ValidationRun; location?: ValidationLocation; original?: boolean }) {
  const sourceLocation = location || { enrollmentId: run.enrollment_id, origin: 'run' as const, reference: run.run_id }
  return <section aria-label={original ? 'Original validation failure' : 'Saved validation run'} className="min-w-0 space-y-3 text-sm">
    <h5 className="text-base font-semibold">{run.phase === 'original' ? 'Original revision' : 'Repaired revision'} · {states[run.state]}</h5>
    <p>Models: {run.model_names.join(', ')}. Both complete sources and all six fields are included.</p>
    <ValidationCaptureEvidence capture={run.input_snapshot} location={sourceLocation} /><ValidationSuiteEvidence suite={run.suite} />
    {run.scope_decision && <p>Saved scope choice: <strong>{run.scope_decision.submission.choice}</strong>. {run.scope_decision.submission.reason}</p>}
    {run.result?.checks && <section aria-label="Source comparisons" className="space-y-3">
      <h6 className="font-semibold">{!run.result.checks.complete ? 'Incomplete evidence · this is not a semantic test failure' : run.result.checks.source_supported ? 'All six expectations and results supported by the sources' : 'Source mismatch · inspect every field below'}</h6>
      {run.result.checks.cases.map(c => <section key={c.source_id} className="space-y-2"><h6 className="font-semibold">{c.source_id.toUpperCase()} comparisons</h6>{c.fields.map(f => <article key={f.field} className="space-y-1 rounded-lg border border-gray-300 px-[6px] py-3 sm:p-3"><p className="font-semibold">{f.field}</p><p>Actual: {f.output_comparable ? f.actual_value === null ? 'Explicit absence' : String(f.actual_value) : 'Unavailable or malformed'}</p><p>Expected value source check: {f.expected_source_supported ? 'Supported' : 'Needs revision'}</p><p>Actual value source check: {f.output_comparable ? f.matches_source ? 'Supported' : 'Mismatch' : 'Unavailable'}</p><p>Matches your saved expectation: {f.output_comparable ? f.matches_learner_expectation ? 'Yes' : 'No' : 'Unknown'}</p></article>)}</section>)}
    </section>}
    {['failed', 'uncertain', 'executing'].includes(run.state) && <p>The saved state does not establish a complete semantic result. Reopening this record never repeats extraction.</p>}
    <details><summary className="min-h-11 cursor-pointer py-2">Inspect actual saved case receipts</summary><EvidenceText label="Validation case receipts" value={run.case_events} /></details>
    {run.original_run && <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Compare the preserved original failure</summary><ValidationRunEvidence run={run.original_run} location={sourceLocation} original /></details>}
    <details><summary className="min-h-11 cursor-pointer py-2">Saved run reference</summary><p className="break-all">{run.run_id}</p></details>
  </section>
}
