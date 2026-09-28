import { useCallback, useEffect, useRef, useState } from 'react'
import { getAutomationHistory, getAutomationRun, type AutomationHistoryCursor } from '../../api/automations'
import type { AutomationRunStatus } from '../../types/automation'

const ACTIVE = new Set(['pending', 'queued', 'running'])
const buttonStyle = { border: '1px solid #9ca3af', borderRadius: 6, padding: '6px 10px', font: 'inherit', fontSize: 13, background: '#fff', color: '#374151', cursor: 'pointer' }
const timestamp = (value: string | null) => value ? new Date(value).toLocaleString() : 'Time unavailable'

interface Props { automationId: string; open: boolean; canRun: boolean; onPrepareRun: () => void }
export function AutomationRunHistory(props: Props) {
  return <HistorySession key={props.automationId} {...props} />
}

function HistorySession({ automationId, open, canRun, onPrepareRun }: Props) {
  const [rows, setRows] = useState<AutomationRunStatus[]>([])
  const [cursor, setCursor] = useState<AutomationHistoryCursor | null>(null)
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [failedCursor, setFailedCursor] = useState<AutomationHistoryCursor | undefined>()
  const [selected, setSelected] = useState<AutomationRunStatus | null>(null)
  const requestVersion = useRef(0)
  const busy = useRef(false)
  const selectedTrigger = useRef<HTMLButtonElement | null>(null)
  const load = useCallback(async (next?: AutomationHistoryCursor) => {
    if (busy.current) return
    busy.current = true
    const version = ++requestVersion.current
    setLoading(true); setError(null)
    try {
      const page = await getAutomationHistory(automationId, next)
      if (requestVersion.current !== version) return
      setRows(old => next ? [...old, ...page.items.filter(row => !old.some(item => item.trigger_event_id === row.trigger_event_id))] : page.items)
      setCursor(page.next_cursor); setLoaded(true)
    } catch (reason) {
      if (requestVersion.current === version) {
        setError(reason instanceof Error ? reason.message : 'Could not load run history.')
        setFailedCursor(next)
      }
    } finally {
      if (requestVersion.current === version) { busy.current = false; setLoading(false) }
    }
  }, [automationId])
  useEffect(() => {
    if (open) void load()
    return () => { requestVersion.current += 1; busy.current = false }
  }, [open, load])

  return <div aria-label="Automation run history" role="region" style={{ fontSize: 13, color: '#374151', overflowWrap: 'anywhere' }}>
    <p style={{ margin: '8px 0' }}>Recorded runs for this automation, newest first. Opening a run checks its status without starting another.</p>
    <button type="button" style={buttonStyle} disabled={loading} onClick={() => void load()}>Refresh history</button>
    {loading && <p role="status">Loading run history…</p>}
    {error && <div role="alert" style={{ marginTop: 12, color: '#b91c1c' }}>
      <p>{error} {rows.length > 0 && 'Previously loaded runs are preserved.'}</p>
      <button type="button" style={buttonStyle} onClick={() => void load(failedCursor)}>Retry history</button>
    </div>}
    {loaded && !loading && !error && rows.length === 0 && <p style={{ marginTop: 12 }}>No recorded runs yet.{canRun && ' Use Run now to test the current configuration.'}</p>}
    <ol style={{ listStyle: 'none', padding: 0, margin: '12px 0', display: 'grid', gap: 8 }}>
      {rows.map(row => <li key={row.trigger_event_id} style={{ border: '1px solid #d1d5db', borderRadius: 8, padding: 12 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
          <strong style={{ textTransform: 'capitalize', color: row.status === 'failed' || row.status === 'error' ? '#b91c1c' : '#374151' }}>{row.status}</strong>
          <span>{row.action_type === 'extraction' ? 'Extraction' : 'Workflow / task'}</span>
          <time dateTime={row.created_at ?? undefined}>{timestamp(row.created_at)}</time>
        </div>
        <p style={{ margin: '6px 0', fontSize: 12 }}>Run {row.trigger_event_id}</p>
        {row.error && <p style={{ color: '#b91c1c', margin: '6px 0' }}>{row.error}</p>}
        <button type="button" style={buttonStyle} aria-label={`Open run ${row.trigger_event_id}`} aria-pressed={selected?.trigger_event_id === row.trigger_event_id} onClick={event => { selectedTrigger.current = event.currentTarget; setSelected(row) }}>
          {ACTIVE.has(row.status) ? 'Watch run' : 'View result'}
        </button>
      </li>)}
    </ol>
    {cursor && <button type="button" style={buttonStyle} disabled={loading} onClick={() => void load(cursor)}>Load older runs</button>}
    {selected && <RunDetails key={selected.trigger_event_id} automationId={automationId} event={selected} open={open} canRun={canRun} onPrepareRun={onPrepareRun} onClose={() => { setSelected(null); selectedTrigger.current?.focus() }} />}
  </div>
}

function RunDetails({ automationId, event, open, canRun, onPrepareRun, onClose }: Omit<Props, 'automationId'> & { automationId: string; event: AutomationRunStatus; onClose: () => void }) {
  const [run, setRun] = useState<AutomationRunStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [checking, setChecking] = useState(true)
  const [attempt, setAttempt] = useState(0)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [])
  useEffect(() => {
    if (!open) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const tick = async () => {
      setChecking(true); setError(null)
      try {
        const result = await getAutomationRun(automationId, event.trigger_event_id)
        if (cancelled) return
        setRun(result)
        if (ACTIVE.has(result.status)) timer = setTimeout(tick, 3000)
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : 'Could not load this run.')
      } finally { if (!cancelled) setChecking(false) }
    }
    void tick()
    return () => { cancelled = true; clearTimeout(timer) }
  }, [automationId, event.trigger_event_id, open, attempt])
  const current = run ?? event
  return <section aria-label={`Run details ${event.trigger_event_id}`} style={{ marginTop: 16, padding: 12, border: '1px solid #9ca3af', borderRadius: 8 }}>
    <h3 ref={heading} tabIndex={-1} style={{ fontSize: 15, margin: '0 0 8px' }}>Run details</h3>
    <p>Run {event.trigger_event_id}</p>
    <p role="status" style={{ margin: '8px 0' }}>{checking && !run ? 'Checking recorded run…' : `${error ? 'Last recorded status' : 'Status'}: ${current.status}`}</p>
    <p>Started: {timestamp(current.started_at)}</p>
    <p>Finished: {timestamp(current.completed_at)}</p>
    {current.error && <p style={{ color: '#b91c1c', marginTop: 8 }}>{current.error}</p>}
    {error && <div role="alert" style={{ marginTop: 8, color: '#b91c1c' }}><p>{error} The run may still finish. Checking again does not launch it again.</p><button type="button" style={buttonStyle} onClick={() => setAttempt(n => n + 1)}>Retry run details</button></div>}
    {run?.output != null && run.output !== '' && <pre role="region" tabIndex={0} aria-label="Recorded run output" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 240, overflowY: 'auto', fontSize: 12, background: '#f9fafb', padding: 10, marginTop: 12 }}>{typeof run.output === 'string' ? run.output : JSON.stringify(run.output, null, 2)}</pre>}
    {run && !ACTIVE.has(run.status) && run.output == null && <p style={{ marginTop: 8 }}>No output was recorded for this run.</p>}
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
      {run && !ACTIVE.has(run.status) && canRun && <button type="button" style={buttonStyle} onClick={onPrepareRun}>Prepare another run</button>}
      <button type="button" style={buttonStyle} onClick={onClose}>Close run details</button>
    </div>
    {run && !ACTIVE.has(run.status) && canRun && <p style={{ marginTop: 8 }}>A new run uses the current trigger, input and output settings. Review them before starting.</p>}
  </section>
}
