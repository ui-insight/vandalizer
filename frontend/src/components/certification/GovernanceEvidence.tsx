import { useEffect, useRef, useState } from 'react'
import { downloadGovernanceFile } from '../../api/governanceAssessment'
import type { GovernanceDownload } from '../../api/governanceAssessment'
import type { GovernanceCapture, GovernanceRun, GovernanceMemo, GovernanceHandoff, GovernanceView } from '../../types/governanceAssessment'
import { EvidenceText } from './ConnectedWorkflowEvidence'
import { governanceLabels } from './governanceAssessmentState'
export { outputButton as governanceButton, outputControl as governanceControl } from './OutputWorkflowEvidence'
import { outputButton as button } from './OutputWorkflowEvidence'
export const governanceBox = 'min-w-0 space-y-3 rounded-lg border border-gray-300 px-[6px] py-3 sm:p-3'
type SourceLocation = { origin: Exclude<GovernanceView['kind'], 'scope'>; reference: string }
type FileLocation = { origin: 'memo' | 'release' | 'handoff' | 'review'; reference: string }
export function GovernanceDownloadButton({ enrollmentId, file, sha256, filename, label }: { enrollmentId: string; file: GovernanceDownload; sha256: string; filename: string; label: string }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [verified, setVerified] = useState(false)
  const active = useRef(true), sending = useRef(false)
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
  async function download() {
    if (sending.current) return
    sending.current = true; setBusy(true); setError('')
    try {
      const blob = await downloadGovernanceFile(enrollmentId, file, sha256)
      if (!active.current) return
      const url = URL.createObjectURL(blob), link = document.createElement('a')
      link.href = url; link.download = filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); setVerified(true)
    } catch { if (active.current) setError('The original file could not be downloaded and verified. Read the saved record and try again.') }
    finally { sending.current = false; if (active.current) setBusy(false) }
  }
  return <div className="space-y-1"><button type="button" className={button} disabled={busy} onClick={() => { void download() }}>{busy ? 'Checking original bytes…' : label}</button>{verified && <p className="text-sm" role="status">Downloaded bytes match the saved file. Inspect its content before recording your judgment.</p>}{error && <p role="alert" className="text-sm text-red-800">{error}</p>}</div>
}
export function GovernanceCaptureEvidence({ capture, location }: { capture: GovernanceCapture; location: SourceLocation }) {
  return <section aria-label="Saved capstone sources and revision" className="min-w-0 space-y-3 text-sm">
    <h5 className="font-semibold">{capture.artifact.title}</h5>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Inspect all six captured instructions</summary>{capture.artifact.fields.map(field => <div key={field.id} className="space-y-1 py-2"><h6 className="font-semibold">{field.title}</h6><p>{field.searchphrase}</p></div>)}</details>
    {capture.documents.map(source => <section key={source.source_id} className="min-w-0 space-y-2"><h6 className="font-semibold">{source.source_id === 'award' ? 'Original award notice' : 'Issued amendment'} · complete fictional source</h6>
      <GovernanceDownloadButton enrollmentId={capture.enrollment_id} file={{ ...location, sourceId: source.source_id }} sha256={source.source_sha256} filename={source.assigned_filename} label={`Download original ${source.source_id} PDF`} />
      <details><summary className="min-h-11 cursor-pointer py-2">Read {source.source_id} source pages</summary>{source.pages.map((page, i) => <div key={i}><p className="py-2 font-semibold">Page {i + 1}</p><EvidenceText label={`${source.source_id} page ${i + 1}`} value={page} /></div>)}</details>
    </section>)}
  </section>
}
const states = { prepared: 'Prepared · not run', executing: 'Started · no final receipt', completed: 'Actual result saved', failed: 'Execution unavailable', uncertain: 'Execution outcome uncertain' }
export function GovernanceRunEvidence({ run, location }: { run: GovernanceRun; location: SourceLocation }) {
  const checks = run.result?.checks
  return <section aria-label="Saved capstone extraction" className="min-w-0 space-y-3 text-sm">
    <h5 className="text-base font-semibold">{run.phase === 'original' ? 'Original diagnostic extraction' : 'Repaired complete extraction'} · {states[run.state]}</h5>
    <p>Models: {run.model_names.join(', ')}. Both complete sources jointly inform one six-field result.</p>
    <GovernanceCaptureEvidence capture={run.input_snapshot} location={location} />
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Your original scope correction</summary><p className="whitespace-pre-wrap">{run.scope_correction.submission.reason}</p><p>Only the assigned source IDs and your private training inbox are in scope. Recurring automation stays disabled.</p></details>
    {run.scope_decision && <p>Saved execution choice: <strong>{run.scope_decision.submission.choice}</strong>. {run.scope_decision.submission.reason}</p>}
    {checks && <section aria-label="Actual capstone source checks" className="space-y-3"><h6 className="font-semibold">{checks.source_supported ? 'All six values match the sources' : checks.observed_semantic_failure ? 'An actual value needs source-grounded repair' : 'Missing or malformed evidence · no semantic failure inferred'}</h6>
      {checks.fields.map(field => <div key={field.field} className="space-y-1 border-t border-gray-200 py-2"><p className="font-semibold">{field.field}</p><EvidenceText label={`${field.field} actual value`} value={field.actual_value} /><p>Source check: {field.output_comparable ? field.matches_source ? 'Supported' : 'Mismatch' : 'Unavailable'}</p></div>)}
    </section>}
    {run.source_finding && <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Preserved original result and your source finding</summary><p className="whitespace-pre-wrap">{run.source_finding.submission.explanation}</p>{run.source_finding.submission.source_references.map((q, i) => <blockquote key={i} className="my-2 border-l-2 border-gray-300 pl-2">{q.source_id}, page {q.page}: {q.quote}</blockquote>)}<GovernanceRunEvidence run={run.source_finding.run} location={location} /></details>}
    {run.result?.repair_checks && <p>Same-extraction repair: {run.result.repair_checks.repair_requirements_supported ? 'Supported by the complete actual rerun' : 'Still unresolved'}. This does not establish general reliability.</p>}
    {['failed', 'uncertain', 'executing'].includes(run.state) && <p>This state does not establish a complete usable result. Read the original saved work before taking further action. Reading never repeats extraction.</p>}
    <details><summary className="min-h-11 cursor-pointer py-2">Inspect exact execution receipts and reference</summary><p className="break-all">{run.run_id}</p><EvidenceText label="Capstone execution receipts" value={run.extraction_events} /></details>
  </section>
}
export function GovernanceMemoEvidence({ memo, source, file }: { memo: GovernanceMemo; source: SourceLocation; file: FileLocation }) {
  return <section aria-label="Accountable capstone memo" className="min-w-0 space-y-3 text-sm"><h5 className="text-base font-semibold">Inspect the accountable memo</h5>
    <p>Responsible training owner: {memo.file.memo.owner_user_id}</p>
    {Object.entries(memo.file.memo.accountability).map(([key, value]) => <div key={key} className="space-y-1"><h6 className="font-semibold capitalize">{key.replaceAll('_', ' ')}</h6><p className="whitespace-pre-wrap">{value}</p></div>)}
    <h6 className="font-semibold">Checked values included in these bytes</h6>{Object.entries(memo.file.memo.results).map(([key, value]) => <div key={key}><strong>{key}</strong><EvidenceText label={key} value={value} /></div>)}
    <GovernanceDownloadButton enrollmentId={memo.enrollment_id} file={file} sha256={memo.file.sha256} filename={memo.file.filename} label="Download exact accountable memo JSON" />
    <details><summary className="min-h-11 cursor-pointer py-2">Inspect the complete structured memo and file identity</summary><p className="break-all">SHA-256: {memo.file.sha256}</p><p>{memo.file.byte_length} bytes</p><EvidenceText label="Complete accountable memo" value={memo.file.memo} /></details>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Inspect preserved source-checked repair</summary><GovernanceRunEvidence run={memo.run} location={source} /></details>
  </section>
}
function HandoffEvidence({ handoff, source, file }: { handoff: GovernanceHandoff; source: SourceLocation; file: FileLocation }) {
  return <section aria-label="Saved private capstone handoff" className="min-w-0 space-y-3 text-sm"><h5 className="text-base font-semibold">{handoff.status === 'delivered' ? 'Same checked memo confirmed in your private inbox' : 'Disclosed training rejection · no destination write'}</h5>
    <p>{handoff.status === 'delivered' ? 'The destination bytes and confirming receipt were saved together. Extraction was not repeated. No external sponsor, email, staff recipient or recurring action was involved.' : 'This first rejection is part of the disclosed training case. It occurred before copying the memo; it is not a real external outage.'}</p>
    <p className="whitespace-pre-wrap">Your release reasoning: {handoff.release.submission.reason}</p>
    <GovernanceMemoEvidence memo={handoff.release.memo} source={source} file={file} />
    {handoff.previous_failed_receipt && <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Preserved first no-write failure</summary><p>Destination written: no. Reason: disclosed training rejection before write.</p><p className="break-all">Original receipt: {handoff.previous_failed_receipt.uuid}</p><p>Original release reasoning: {handoff.previous_failed_receipt.release.submission.reason}</p></details>}
  </section>
}
export function GovernanceEvidence({ view }: { view: GovernanceView }) {
  if (view.kind === 'scope') return <section className="space-y-3"><h5 className="font-semibold">Saved execution choice: {view.value.submission.choice}</h5><p className="whitespace-pre-wrap text-sm">{view.value.submission.reason}</p></section>
  const source: SourceLocation = { origin: view.kind, reference: view.kind === 'run' ? view.value.run_id : view.value.uuid }
  return <div className="min-w-0 space-y-3"><h4 className="text-lg font-semibold">{governanceLabels[view.kind]}</h4>
    {view.kind === 'capture' && <GovernanceCaptureEvidence capture={view.value} location={source} />}
    {view.kind === 'run' && <GovernanceRunEvidence run={view.value} location={source} />}
    {view.kind === 'correction' && <><p className="whitespace-pre-wrap text-sm">{view.value.submission.reason}</p><p className="text-sm">Saved before the original extraction. Only the two assigned records and your private inbox are in scope; recurring actions remain disabled.</p><GovernanceCaptureEvidence capture={view.value.input_snapshot} location={source} /></>}
    {view.kind === 'finding' && <><p className="whitespace-pre-wrap text-sm">{view.value.submission.explanation}</p>{view.value.submission.source_references.map((q, i) => <blockquote key={i} className="border-l-2 border-gray-300 pl-2 text-sm">{q.source_id}, page {q.page}: {q.quote}</blockquote>)}<GovernanceRunEvidence run={view.value.run} location={source} /></>}
    {view.kind === 'memo' && <GovernanceMemoEvidence memo={view.value} source={source} file={{ origin: 'memo', reference: view.value.uuid }} />}
    {view.kind === 'release' && <><p className="font-semibold">Release choice: {view.value.submission.choice}</p><p className="whitespace-pre-wrap text-sm">{view.value.submission.reason}</p><GovernanceMemoEvidence memo={view.value.memo} source={source} file={{ origin: 'release', reference: view.value.uuid }} /></>}
    {view.kind === 'handoff' && <HandoffEvidence handoff={view.value} source={source} file={{ origin: 'handoff', reference: view.value.uuid }} />}
    {view.kind === 'review' && <><p className="whitespace-pre-wrap text-sm">{view.value.submission.final_supervision}</p>{view.value.submission.previous_submission_id && <p className="break-all text-sm">Earlier answer reference: {view.value.submission.previous_submission_id}</p>}<HandoffEvidence handoff={view.value.handoff} source={source} file={{ origin: 'review', reference: view.value.uuid }} /></>}
    <details><summary className="min-h-11 cursor-pointer py-2 text-sm">Saved record reference</summary><p className="break-all text-sm">{source.reference}</p></details>
  </div>
}
