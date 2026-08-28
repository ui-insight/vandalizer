import { useEffect, useRef, useState } from 'react'
import { Play, Loader2, CheckCircle, XCircle, AlertTriangle, X, FileText, Search } from 'lucide-react'
import { runAutomationNow, getAutomationRun } from '../../api/automations'
import { searchDocuments } from '../../api/documents'
import type { Automation, RunNowResponse, AutomationRunStatus } from '../../types/automation'

/**
 * "Run now": run an automation once, immediately, through its real pipeline.
 *
 * The point is to test the parts a workflow run alone cannot — which
 * documents the trigger picks up, whether the result lands in the right
 * folder in the right format, whether notifications and webhooks fire — so
 * this is deliberately a real run, and the panel says so before the click.
 * Folder-watch and schedule automations run on what their trigger would
 * pick; API and M365 automations have no documents until something arrives,
 * so those ask the user to choose.
 */

export const TRIGGERS_NEEDING_DOCUMENTS = new Set(['api', 'm365_intake'])
const TERMINAL = new Set(['completed', 'failed', 'skipped', 'error', 'canceled'])
const POLL_MS = 3000

export function describeRunNowSource(automation: Pick<Automation, 'trigger_type' | 'trigger_config'>): string {
  const cfg = automation.trigger_config || {}
  switch (automation.trigger_type) {
    case 'folder_watch':
      return cfg.folder_id
        ? 'Runs on the documents currently in the watched folder that pass this automation’s file filters (newest first, up to 25).'
        : 'Choose a watched folder in Trigger first, or pick documents below.'
    case 'schedule':
      return 'Runs on the documents this schedule is configured with.'
    default:
      return 'This trigger receives its documents when it fires, so choose the documents to run with.'
  }
}

export function describeRunNowResult(run: AutomationRunStatus): { tone: 'ok' | 'bad' | 'warn'; text: string } {
  if (run.status === 'completed') {
    return { tone: 'ok', text: 'Run completed. Outputs were delivered per this automation’s settings — check the destination folder, your notifications, and any webhook receiver.' }
  }
  if (run.status === 'skipped') {
    return { tone: 'warn', text: `Run skipped${run.error ? `: ${run.error}` : ''}.` }
  }
  return { tone: 'bad', text: `Run ${run.status}${run.error ? `: ${run.error}` : ''}.` }
}

interface Props {
  automation: Automation
  canManage: boolean
  onClose: () => void
}

export function AutomationRunNowPanel({ automation, canManage, onClose }: Props) {
  const needsDocs = TRIGGERS_NEEDING_DOCUMENTS.has(automation.trigger_type)
    || (automation.trigger_type === 'folder_watch' && !automation.trigger_config?.folder_id)
  const [chosen, setChosen] = useState<{ uuid: string; title: string }[]>([])
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<{ uuid: string; title: string }[]>([])
  const [showResults, setShowResults] = useState(false)
  const [starting, setStarting] = useState(false)
  const [started, setStarted] = useState<RunNowResponse | null>(null)
  const [run, setRun] = useState<AutomationRunStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Document search for triggers that have no documents of their own.
  useEffect(() => {
    if (!needsDocs || !showResults) return
    const q = query.trim()
    const t = setTimeout(async () => {
      try {
        const res = await searchDocuments(q, 20)
        setResults(res.items.map(d => ({ uuid: d.uuid, title: d.title })).filter(d => !chosen.some(c => c.uuid === d.uuid)))
      } catch {
        setResults([])
      }
    }, q ? 250 : 0)
    return () => clearTimeout(t)
  }, [query, showResults, needsDocs, chosen])

  // Poll the run until it settles.
  useEffect(() => {
    if (!started) return
    const tick = async () => {
      try {
        const status = await getAutomationRun(automation.id, started.trigger_event_id)
        setRun(status)
        if (TERMINAL.has(status.status) && pollRef.current) {
          clearInterval(pollRef.current)
          pollRef.current = null
        }
      } catch {
        // keep polling — a transient fetch failure is not a run failure
      }
    }
    void tick()
    pollRef.current = setInterval(tick, POLL_MS)
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }
  }, [started, automation.id])

  const handleRun = async () => {
    setError(null)
    setRun(null)
    setStarting(true)
    try {
      const res = await runAutomationNow(automation.id, chosen.map(c => c.uuid))
      setStarted(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start the run')
    } finally {
      setStarting(false)
    }
  }

  const disabled = !canManage || starting || (needsDocs && chosen.length === 0) || !automation.action_id
  const inFlight = !!started && (!run || !TERMINAL.has(run.status))
  const result = run && TERMINAL.has(run.status) ? describeRunNowResult(run) : null

  return (
    <section
      aria-label="Run now"
      style={{
        border: '1px solid #fde68a', backgroundColor: '#fffbeb', borderRadius: 8,
        padding: 16, marginBottom: 20,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: 8 }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#202124', display: 'flex', alignItems: 'center', gap: 6 }}>
            <Play style={{ width: 14, height: 14 }} /> Run now
          </div>
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>{describeRunNowSource(automation)}</div>
        </div>
        <button type="button" onClick={onClose} aria-label="Close run now" style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', padding: 2 }}>
          <X style={{ width: 16, height: 16 }} />
        </button>
      </div>

      <div role="note" style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 12, color: '#92400e', marginBottom: 12 }}>
        <AlertTriangle style={{ width: 14, height: 14, flexShrink: 0, marginTop: 1 }} />
        <span>
          This is a real run, not a dry run: results are saved and notifications and webhooks are sent exactly as configured below.
          {!automation.enabled && ' The automation can stay disabled — a manual run does not switch it on.'}
        </span>
      </div>

      {needsDocs && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 6 }}>Documents to run with</div>
          {chosen.length > 0 && (
            <ul style={{ listStyle: 'none', margin: '0 0 6px', padding: 0, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {chosen.map(d => (
                <li key={d.uuid} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', fontSize: 12, backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: 999 }}>
                  <FileText style={{ width: 12, height: 12, color: '#6b7280' }} />
                  {d.title}
                  <button type="button" aria-label={`Remove ${d.title}`} onClick={() => setChosen(c => c.filter(x => x.uuid !== d.uuid))} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: '#6b7280', display: 'flex' }}>
                    <X style={{ width: 12, height: 12 }} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div style={{ position: 'relative' }}>
            <Search style={{ width: 13, height: 13, position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', color: '#6b7280' }} />
            <input
              aria-label="Search documents to run with"
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onFocus={() => setShowResults(true)}
              onBlur={() => setTimeout(() => setShowResults(false), 200)}
              placeholder="Search your library…"
              style={{ width: '100%', padding: '6px 10px 6px 26px', fontSize: 12, fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6, outline: 'none', boxSizing: 'border-box' }}
            />
            {showResults && (
              <div role="listbox" aria-label="Documents" style={{ position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 4, backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: 6, boxShadow: '0 8px 24px rgba(0,0,0,0.12)', zIndex: 10, maxHeight: 180, overflowY: 'auto' }}>
                {results.length === 0 ? (
                  <div style={{ padding: '6px 10px', fontSize: 12, color: '#6b7280' }}>No documents found</div>
                ) : results.map(d => (
                  <div key={d.uuid} role="option" aria-selected={false} onMouseDown={() => { setChosen(c => [...c, d]); setQuery('') }} style={{ padding: '6px 10px', fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <FileText style={{ width: 12, height: 12, color: '#6b7280' }} />
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.title}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <button
          type="button"
          onClick={handleRun}
          disabled={disabled || inFlight}
          title={!automation.action_id ? 'Choose an action first' : !canManage ? 'Only the creator or a team owner/admin can run this' : undefined}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 14px',
            fontSize: 13, fontWeight: 700, fontFamily: 'inherit', border: 'none', borderRadius: 6,
            backgroundColor: 'var(--highlight-color, #eab308)', color: 'var(--highlight-text-color, #000)',
            cursor: disabled || inFlight ? 'not-allowed' : 'pointer', opacity: disabled || inFlight ? 0.6 : 1,
          }}
        >
          {starting || inFlight ? <Loader2 style={{ width: 14, height: 14, animation: 'spin 1s linear infinite' }} /> : <Play style={{ width: 14, height: 14 }} />}
          {inFlight ? 'Running…' : started ? 'Run again' : 'Run now'}
        </button>
        {started && (
          <span style={{ fontSize: 12, color: '#6b7280' }}>
            {started.documents.length} document{started.documents.length !== 1 ? 's' : ''}
            {started.document_source === 'folder' && started.documents_matched > started.documents.length
              ? ` (first ${started.documents.length} of ${started.documents_matched} in the folder)` : ''}
            : {started.documents.map(d => d.title).join(', ')}
          </span>
        )}
      </div>

      {error && (
        <div role="alert" style={{ marginTop: 10, display: 'flex', gap: 6, alignItems: 'flex-start', fontSize: 13, color: '#b91c1c' }}>
          <XCircle style={{ width: 14, height: 14, flexShrink: 0, marginTop: 2 }} />{error}
        </div>
      )}
      {inFlight && (
        <div role="status" style={{ marginTop: 10, fontSize: 12, color: '#6b7280' }}>
          Started — {run?.status ?? 'queued'}. This panel updates as the run progresses.
        </div>
      )}
      {result && (
        <div role="status" style={{
          marginTop: 10, display: 'flex', gap: 6, alignItems: 'flex-start', fontSize: 13,
          color: result.tone === 'ok' ? '#166534' : result.tone === 'warn' ? '#92400e' : '#b91c1c',
        }}>
          {result.tone === 'ok'
            ? <CheckCircle style={{ width: 14, height: 14, flexShrink: 0, marginTop: 2 }} />
            : <XCircle style={{ width: 14, height: 14, flexShrink: 0, marginTop: 2 }} />}
          <span>{result.text}</span>
        </div>
      )}
      {result && run?.output != null && run.output !== '' && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ cursor: 'pointer', fontSize: 12, fontWeight: 600, color: '#374151' }}>Output</summary>
          <pre style={{ margin: '6px 0 0', fontSize: 11, whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 240, overflowY: 'auto', backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: 6, padding: 8 }}>
            {typeof run.output === 'string' ? run.output : JSON.stringify(run.output, null, 2)}
          </pre>
        </details>
      )}
    </section>
  )
}
