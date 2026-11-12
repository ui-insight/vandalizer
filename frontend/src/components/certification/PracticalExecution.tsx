import { useEffect, useRef, useState } from 'react'
import { executePracticalRun, getPracticalExecution } from '../../api/certification'
import type { PracticalExecutionBody, SavedPracticalExecution } from '../../types/certification'

const button = 'min-h-11 min-w-0 max-w-full rounded-lg border border-gray-300 bg-white px-2 py-2 text-left text-sm font-medium text-gray-900 [overflow-wrap:anywhere] disabled:opacity-50 sm:px-4'
const messages = {
  prepared: 'Saved run is prepared', executing: 'Execution is in progress', completed: 'Execution result saved',
  failed: 'Execution could not finish', uncertain: 'Execution status is uncertain',
}

export function PracticalExecution({ enrollmentId, moduleId, runId, onChanged, onReviewResult }: {
  enrollmentId: string; moduleId: string; runId: string; onChanged: () => void; onReviewResult: () => void
}) {
  const key = `certification-execution:${enrollmentId}:${runId}`
  const [pending, setPending] = useState(() => { try { return sessionStorage.getItem(key) !== null } catch { return false } })
  const [receipt, setReceipt] = useState<SavedPracticalExecution | null>(null)
  const [busy, setBusy] = useState(false)
  const [requestingExecution, setRequestingExecution] = useState(false)
  const [error, setError] = useState('')
  const sending = useRef(false), sequence = useRef(0)
  const resultRef = useRef<HTMLDivElement>(null)
  useEffect(() => () => { sequence.current++ }, [enrollmentId, moduleId, runId])

  function verify(value: SavedPracticalExecution, expected?: PracticalExecutionBody) {
    if (value.enrollment_id !== enrollmentId || value.module_id !== moduleId || value.run_id !== runId
      || !Object.hasOwn(messages, value.state) || !/^[a-f0-9]{64}$/.test(value.plan_sha256)
      || typeof value.can_execute !== 'boolean' || value.credit_awarded !== false || value.module_completion_eligible !== false
      || value.result_available !== (value.state === 'completed')
      || (value.can_execute && (value.state !== 'prepared' || !/^[a-f0-9]{32}$/.test(value.scope_decision_id || '') || !/^[a-f0-9]{64}$/.test(value.scope_decision_sha256 || '')))
      || (expected && (value.plan_sha256 !== expected.plan_sha256 || value.scope_decision_id !== expected.scope_decision_id || value.scope_decision_sha256 !== expected.scope_decision_sha256))) {
      throw new Error('Execution receipt does not match this run')
    }
    return value
  }

  async function act(execute: boolean) {
    if (sending.current || (execute && (pending || !receipt?.can_execute))) return
    sending.current = true
    const token = ++sequence.current
    setBusy(true); setRequestingExecution(execute); setError('')
    let sent = false
    try {
      let value: SavedPracticalExecution
      if (execute) {
        const body: PracticalExecutionBody = { plan_sha256: receipt!.plan_sha256, scope_decision_id: receipt!.scope_decision_id!, scope_decision_sha256: receipt!.scope_decision_sha256!, consent: 'execute_saved_inputs' }
        sessionStorage.setItem(key, JSON.stringify(body)); setPending(true)
        sent = true
        value = verify(await executePracticalRun(enrollmentId, runId, body), body)
      } else value = verify(await getPracticalExecution(enrollmentId, runId))
      if (token !== sequence.current) return
      sessionStorage.removeItem(key); setPending(false); setReceipt(value)
      onChanged()
      requestAnimationFrame(() => { if (token === sequence.current) resultRef.current?.focus() })
    } catch {
      if (token !== sequence.current) return
      setReceipt(null)
      setError(execute && !sent
        ? 'This browser could not preserve the run reference. Allow session storage before running; no execution request was sent.'
        : 'We could not confirm the saved execution state. Check its status before trying to run again. Checking status does not start or repeat execution.')
    } finally { sending.current = false; if (token === sequence.current) setBusy(false) }
  }

  return <section className="min-w-0 space-y-3 border-t border-gray-200 pt-4 [overflow-wrap:anywhere]" aria-label="Execute saved practical run">
    <h5 className="text-base font-semibold text-gray-900">Execute your saved run</h5>
    <p className="text-sm text-gray-700">Check the saved plan and scope approval before starting. Running uses the configured models and may incur model usage. It uses your saved inputs, even if the workspace has changed.</p>
    {pending && <p className="text-sm text-amber-900">An execution request awaits confirmation. Check the same run before taking another action.</p>}
    <button type="button" className={button} disabled={busy} onClick={() => { void act(false) }}>Check execution status</button>
    {busy && <p role="status" className="text-sm text-gray-700">{requestingExecution ? 'Sending the execution request and waiting for its saved result…' : 'Checking the saved execution state…'}</p>}
    {(pending || busy && requestingExecution) && <p className="text-sm text-gray-700">Closing this panel does not confirm whether execution finished or stopped. Reopen this saved run and check its status before requesting more work.</p>}
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    {receipt && <div ref={resultRef} tabIndex={-1} role="region" aria-label="Saved execution status" className="min-w-0 space-y-3 outline-offset-4">
      <h6 className="text-sm font-semibold text-gray-900">{pending ? `Last confirmed: ${messages[receipt.state]}` : messages[receipt.state]}</h6>
      <p className="text-sm text-gray-700">Planned models: {receipt.model_names.join(', ')}</p>
      {receipt.blocked_reason && <p className="text-sm text-gray-700">{receipt.blocked_reason}</p>}
      {receipt.can_execute && !pending && <>
        <p className="text-sm text-gray-700">The saved approval matches this plan. Start only when you are ready to run these inputs. If the response times out, check this same run; the provider may still be working.</p>
        <button type="button" className={button} disabled={busy || pending} onClick={() => { void act(true) }}>Run these saved inputs</button>
      </>}
      {receipt.state === 'executing' && <p className="text-sm text-gray-700">This run has already started. Check its status again later; no additional execution is sent.</p>}
      {receipt.state === 'uncertain' && <p className="text-sm text-gray-700">The provider may still be working. This run will not be automatically retried. Keep its reference and check again later. This is not a failed assessment.</p>}
      {receipt.state === 'failed' && <p className="text-sm text-gray-700">The execution failed for a technical reason. Your saved inputs and decisions are preserved. This is not a failed assessment, and this run will not be retried.</p>}
      {receipt.state === 'completed' && <>
        <p className="text-sm text-gray-700">Executed documents: {receipt.documents_executed}. Review the saved values against their sources next.</p>
        <button type="button" className={button} disabled={busy} onClick={() => { sequence.current++; onReviewResult() }}>Review saved values</button>
      </>}
      <p className="text-sm text-gray-700">Execution does not award credit or complete this module.</p>
      <details className="text-sm text-gray-700"><summary className="min-h-11 cursor-pointer py-2">Execution reference</summary>
        <p className="break-all">Run: {receipt.run_id}</p><p className="break-all">Scope decision: {receipt.scope_decision_id || 'Not recorded'}</p>
      </details>
    </div>}
  </section>
}
