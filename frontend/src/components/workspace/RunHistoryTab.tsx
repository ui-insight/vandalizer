import { Link } from '@tanstack/react-router'
import { useCallback, useEffect, useRef, useState } from 'react'
import { CheckCircle, XCircle, Loader2, Clock, FileText, ChevronDown, ChevronRight, Zap, Download, ClipboardCheck, Cpu } from 'lucide-react'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { relativeTime } from '../../utils/time'
import { getWorkflowStatus, downloadResults } from '../../api/workflows'
import type { WorkflowCitation, WorkflowSourcing } from '../../types/workflow'
import { CitedMarkdown } from './CitedMarkdown'
import { useSourcing } from './Sourcing'
import { FileOutputCard } from './FileOutputCard'
import { summarizeFilePayload } from './outputFilePayload'

export interface HistoryRun {
  id: string
  status: string
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  error: string
  tokens_input: number
  tokens_output: number
  documents_touched: number
  steps_completed?: number
  steps_total?: number
  session_id?: string
  result_snapshot: Record<string, unknown>
  /** Set while the run is parked on an approval gate — links to the review. */
  pending_review_uuid?: string | null
  /** Models the run's calls used, most tokens first; empty for runs recorded
   * before models were. */
  models?: string[]
  /** Workflow runs: each step's models, in step order. */
  step_models?: { index: number; name: string | null; models: string[] }[]
}

/** The History tab as a CSV: one row per run, with its model(s) and, for a
 * workflow, which step used which — for comparing models across runs. */
export function buildHistoryCSV(runs: HistoryRun[], type: 'workflow' | 'extraction'): string {
  const escape = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const header = ['Started', 'Finished', 'Status', 'Duration (ms)', 'Input tokens', 'Output tokens', 'Documents', 'Models',
    ...(type === 'workflow' ? ['Models by step'] : []), 'Error']
  const rows = runs.map(run => [
    run.started_at, run.finished_at, run.status, run.duration_ms, run.tokens_input, run.tokens_output,
    run.documents_touched, (run.models ?? []).join('; '),
    ...(type === 'workflow'
      ? [(run.step_models ?? []).map(s => `${s.name ?? `Step ${s.index + 1}`}: ${s.models.join(', ')}`).join('; ')]
      : []),
    run.error,
  ].map(escape).join(','))
  return [header.map(escape).join(','), ...rows].join('\n') + '\n'
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  const secs = ms / 1000
  if (secs < 60) return `${secs.toFixed(1)}s`
  const mins = Math.floor(secs / 60)
  const remSecs = Math.round(secs % 60)
  return `${mins}m ${remSecs}s`
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'awaiting approval') return <ClipboardCheck style={{ width: 14, height: 14, color: '#a16207', flexShrink: 0 }} />
  if (status === 'completed') return <CheckCircle style={{ width: 14, height: 14, color: '#16a34a', flexShrink: 0 }} />
  if (status === 'failed' || status === 'error') return <XCircle style={{ width: 14, height: 14, color: '#dc2626', flexShrink: 0 }} />
  if (status === 'running' || status === 'queued') return <Loader2 style={{ width: 14, height: 14, color: '#2563eb', flexShrink: 0, animation: 'spin 1s linear infinite' }} />
  return <Clock style={{ width: 14, height: 14, color: '#9ca3af', flexShrink: 0 }} />
}

function ResultPreview({ snapshot, type }: { snapshot: Record<string, unknown>; type: 'workflow' | 'extraction' }) {
  if (!snapshot || Object.keys(snapshot).length === 0) return null

  if (type === 'extraction') {
    const normalized = snapshot.normalized as Record<string, unknown> | undefined
    if (!normalized || Object.keys(normalized).length === 0) return null
    const entries = Object.entries(normalized)
    return (
      <div style={{ marginTop: 8, fontSize: 12, color: '#374151' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <tbody>
            {entries.map(([key, val]) => (
              <tr key={key}>
                <td style={{ padding: '3px 8px 3px 0', color: '#6b7280', fontWeight: 500, verticalAlign: 'top', whiteSpace: 'nowrap' }}>{key}</td>
                <td style={{ padding: '3px 0', wordBreak: 'break-word' }}>{val != null ? String(val) : <span style={{ color: '#d1d5db' }}>--</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  // Workflow: just show a summary of what's in the snapshot
  const keys = Object.keys(snapshot)
  if (keys.length === 0) return null
  return (
    <div style={{ marginTop: 8, fontSize: 12, color: '#6b7280' }}>
      {keys.length} result field{keys.length !== 1 ? 's' : ''}
    </div>
  )
}

// Same markdown pipeline the run panel uses for live results, so a historical
// run reads identically to the run that produced it.
function renderMarkdownOutput(data: unknown): string {
  if (data === null || data === undefined) return ''
  let md: string
  if (typeof data === 'string') {
    md = data
  } else {
    try { md = '```json\n' + JSON.stringify(data, null, 2) + '\n```' } catch { md = String(data) }
  }
  return DOMPurify.sanitize(marked.parse(md) as string)
}

const DOWNLOAD_FORMATS = [
  { fmt: 'json', label: 'JSON', desc: 'Structured data', parseStructured: false },
  { fmt: 'csv', label: 'CSV', desc: 'Spreadsheet format', parseStructured: false },
  { fmt: 'csv', label: 'CSV (parse structured)', desc: 'Detect JSON/tables in prompt output', parseStructured: true },
  { fmt: 'pdf', label: 'PDF', desc: 'Printable report', parseStructured: false },
  { fmt: 'docx', label: 'Word (.docx)', desc: 'Editable document', parseStructured: false },
  { fmt: 'markdown', label: 'Markdown', desc: 'Formatted text (.md)', parseStructured: false },
  { fmt: 'text', label: 'Plain Text', desc: 'Raw text output', parseStructured: false },
] as const

// Historical workflow runs don't carry their output in the history payload
// (it can be arbitrarily large) — fetch it from the persisted WorkflowResult
// by session_id when the row is first expanded.
function WorkflowRunOutput({ sessionId }: { sessionId: string }) {
  const [loading, setLoading] = useState(true)
  const [unavailable, setUnavailable] = useState(false)
  const [output, setOutput] = useState<unknown>(null)
  const [citations, setCitations] = useState<WorkflowCitation[]>([])
  const [sourcing, setSourcing] = useState<WorkflowSourcing | null>(null)
  const [showDownload, setShowDownload] = useState(false)
  // Where each statement of the deliverable came from, as in the run view.
  const src = useSourcing(sourcing, 'final')

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    let polls = 0
    // A run that has only just finished may still be tracing its sources,
    // or not have queued the trace yet; pick them up as they land (bounded
    // by the trace's ten-minute budget).
    const waitForSources = (s: WorkflowSourcing | null | undefined) => {
      const waiting = s ? s.status === 'pending' || s.status === 'running' : polls < 3
      if (cancelled || !waiting || polls++ > 300) return
      timer = setTimeout(() => {
        getWorkflowStatus(sessionId)
          .then(next => {
            if (cancelled) return
            setSourcing(next?.sourcing ?? null)
            waitForSources(next?.sourcing)
          })
          .catch(() => waitForSources(s))
      }, 2000)
    }
    getWorkflowStatus(sessionId)
      .then(status => {
        if (cancelled) return
        const fo = status?.final_output as Record<string, unknown> | null
        setOutput(fo && typeof fo === 'object' && 'output' in fo ? fo.output : fo)
        setCitations(status?.retrieved_sources ?? [])
        setSourcing(status?.sourcing ?? null)
        setLoading(false)
        waitForSources(status?.sourcing)
      })
      .catch(() => {
        if (cancelled) return
        setUnavailable(true)
        setLoading(false)
      })
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [sessionId])

  if (loading) {
    return (
      <div role="status" aria-label="Loading run output" style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, fontSize: 12, color: '#6b7280' }}>
        <Loader2 style={{ width: 12, height: 12, animation: 'spin 1s linear infinite' }} />
        Loading output...
      </div>
    )
  }

  if (unavailable || output == null) {
    return (
      <div style={{ marginTop: 8, fontSize: 12, color: '#9ca3af' }}>
        Output is no longer available for this run.
      </div>
    )
  }

  const file = summarizeFilePayload(output)
  const outputStyle = {
    backgroundColor: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 6,
    padding: 12, fontSize: 13, lineHeight: 1.6,
    maxHeight: '50vh', overflowY: 'auto' as const, overflowX: 'auto' as const,
    color: '#374151', wordBreak: 'break-word' as const,
  }
  return (
    <div style={{ marginTop: 8 }}>
      {!file && src.summary}
      {file ? (
        <FileOutputCard summary={file} downloadHref={downloadResults(sessionId, 'text')} maxHeight="50vh" />
      ) : typeof output === 'string' ? (
        // The same rendering as the run view: knowledge-base citation chips,
        // and each traced statement underlined, opening its source.
        <CitedMarkdown
          markdown={output}
          sources={citations}
          className="chat-markdown"
          style={outputStyle}
          sourcing={src.text}
        />
      ) : (
        <div
          className="chat-markdown"
          style={outputStyle}
          dangerouslySetInnerHTML={{ __html: renderMarkdownOutput(output) }}
        />
      )}
      {src.popover}
      <div style={{ position: 'relative', display: 'inline-block', marginTop: 8 }}>
        <button
          onClick={() => setShowDownload(s => !s)}
          aria-expanded={showDownload}
          style={{
            display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px',
            fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
            border: '1px solid #d1d5db', borderRadius: 6,
            backgroundColor: '#fff', cursor: 'pointer', color: '#374151',
          }}
        >
          <Download style={{ width: 12, height: 12 }} />
          Download
        </button>
        {showDownload && (
          <div style={{
            position: 'absolute', bottom: '100%', left: 0, marginBottom: 4,
            backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
            boxShadow: '0 8px 24px rgba(0,0,0,0.12)', zIndex: 10, minWidth: 200,
            padding: '4px 0',
          }}>
            {DOWNLOAD_FORMATS.map(({ fmt, label, desc, parseStructured }) => (
              <a
                key={label}
                href={downloadResults(sessionId, fmt, { parseStructured })}
                onClick={() => setShowDownload(false)}
                style={{
                  display: 'flex', flexDirection: 'column', gap: 1,
                  padding: '8px 14px', fontSize: 13, fontWeight: 500,
                  color: '#374151', textDecoration: 'none',
                  transition: 'background-color 0.1s',
                }}
                onMouseEnter={e => { e.currentTarget.style.backgroundColor = '#f3f4f6' }}
                onMouseLeave={e => { e.currentTarget.style.backgroundColor = '#fff' }}
              >
                <span>{label}</span>
                <span style={{ fontSize: 11, color: '#6b7280', fontWeight: 400 }}>{desc}</span>
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function RunRow({ run, type }: { run: HistoryRun; type: 'workflow' | 'extraction' }) {
  const [expanded, setExpanded] = useState(false)
  // A run parked on an approval gate keeps the activity status "running", which
  // reads as a run that has been going for three days. The marker is the only
  // thing that distinguishes it, so the row relabels itself and offers the one
  // link that moves the run forward.
  // Only a live run can still be waiting on a reviewer. The marker records the
  // pause, not that it is ongoing, and several exits leave it behind — so
  // without this a canceled or failed run shows an amber "awaiting approval"
  // pill over its real status, plus a link to a review nobody can act on.
  const runIsLive = run.status === 'running' || run.status === 'queued'
  const reviewUuid = runIsLive ? (run.pending_review_uuid || null) : null
  const displayStatus = reviewUuid ? 'awaiting approval' : run.status
  const hasSnapshot = run.result_snapshot && Object.keys(run.result_snapshot).length > 0
  // Workflow runs don't snapshot their output into the history payload — the
  // full result is fetched by session_id on expand instead.
  const canFetchOutput = type === 'workflow' && run.status === 'completed' && !!run.session_id
  const models = run.models ?? []
  // Shown when the steps differ — a per-step override, or a fallback model.
  // One model throughout is already said on the row.
  const stepModels = (run.step_models ?? []).filter(s => s.models.length > 0)
  const showStepModels = type === 'workflow' && stepModels.length > 0 && models.length > 1
  // A failed run's step models are the thing to look at when a model misbehaves.
  const hasResults = hasSnapshot || canFetchOutput || showStepModels

  return (
    <div style={{
      borderBottom: '1px solid #f3f4f6',
    }}>
      <button
        onClick={() => hasResults && setExpanded(e => !e)}
        aria-expanded={hasResults ? expanded : undefined}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '12px 24px',
          background: 'none',
          border: 'none',
          cursor: hasResults ? 'pointer' : 'default',
          fontFamily: 'inherit',
          textAlign: 'left',
        }}
      >
        <StatusIcon status={displayStatus} />

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 500, color: '#202124' }}>
              {run.started_at ? relativeTime(run.started_at) : 'Unknown'}
            </span>
            <span style={{
              fontSize: 11,
              fontWeight: 500,
              padding: '1px 6px',
              borderRadius: 4,
              backgroundColor: reviewUuid ? '#fef3c7' : run.status === 'completed' ? '#dcfce7' : run.status === 'failed' || run.status === 'error' ? '#fef2f2' : '#f3f4f6',
              color: reviewUuid ? '#92400e' : run.status === 'completed' ? '#166534' : run.status === 'failed' || run.status === 'error' ? '#991b1b' : '#6b7280',
            }}>
              {displayStatus}
            </span>
          </div>

          <div style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: 11, color: '#6b7280' }}>
            {run.duration_ms != null && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <Clock style={{ width: 11, height: 11 }} />
                {formatDuration(run.duration_ms)}
              </span>
            )}
            {run.documents_touched > 0 && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <FileText style={{ width: 11, height: 11 }} />
                {run.documents_touched} doc{run.documents_touched !== 1 ? 's' : ''}
              </span>
            )}
            {type === 'workflow' && run.steps_total != null && run.steps_total > 0 && (
              <span>
                {run.steps_completed ?? 0}/{run.steps_total} steps
              </span>
            )}
            {(run.tokens_input > 0 || run.tokens_output > 0) && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <Zap style={{ width: 11, height: 11 }} />
                {(run.tokens_input + run.tokens_output).toLocaleString()} tokens
              </span>
            )}
            {models.length > 0 && (
              <span title={models.length > 1 ? `Models used: ${models.join(', ')}` : 'Model used'} style={{ display: 'flex', alignItems: 'center', gap: 3, minWidth: 0 }}>
                <Cpu aria-hidden="true" style={{ width: 11, height: 11, flexShrink: 0 }} />
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{models.join(', ')}</span>
              </span>
            )}
          </div>

          {run.error && (
            <div style={{ fontSize: 12, color: '#dc2626', marginTop: 4 }}>
              {run.error.length > 120 ? run.error.slice(0, 120) + '...' : run.error}
            </div>
          )}
        </div>

        {hasResults && (
          expanded
            ? <ChevronDown style={{ width: 14, height: 14, color: '#9ca3af', flexShrink: 0 }} />
            : <ChevronRight style={{ width: 14, height: 14, color: '#9ca3af', flexShrink: 0 }} />
        )}
      </button>

      {/* Outside the button on purpose — an anchor nested in a button is
          invalid markup and swallows the link's own keyboard activation. */}
      {reviewUuid && (
        <Link
          to={'/reviews/$uuid' as never}
          params={{ uuid: reviewUuid } as never}
          style={{
            display: 'inline-block', margin: '-6px 0 12px 48px',
            fontSize: 12, fontWeight: 600, color: '#0ea5e9', textDecoration: 'none',
          }}
        >
          Open review →
        </Link>
      )}

      {expanded && hasResults && (
        <div style={{ padding: '0 24px 12px 48px' }}>
          {showStepModels && (
            <table aria-label="Models by step" style={{ marginTop: 4, fontSize: 12, color: '#374151', borderCollapse: 'collapse' }}>
              <tbody>
                {stepModels.map(s => (
                  <tr key={s.index}>
                    <td style={{ padding: '2px 12px 2px 0', color: '#6b7280', whiteSpace: 'nowrap', verticalAlign: 'top' }}>{s.name ?? `Step ${s.index + 1}`}</td>
                    <td style={{ padding: '2px 0', wordBreak: 'break-word' }}>{s.models.join(', ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {canFetchOutput
            ? <WorkflowRunOutput sessionId={run.session_id!} />
            : hasSnapshot && <ResultPreview snapshot={run.result_snapshot} type={type} />}
        </div>
      )}
    </div>
  )
}

export function RunHistoryTab({
  fetchHistory,
  historyKey,
  type,
}: {
  fetchHistory: () => Promise<{ runs: HistoryRun[] }>
  /** What the history is of (a workflow or extraction id). The list is
   *  fetched again only when this changes: callers pass a new
   *  `fetchHistory` closure on every render, and refetching on each one
   *  blanked the list and collapsed the run a user had just opened. */
  historyKey?: string
  type: 'workflow' | 'extraction'
}) {
  const [runs, setRuns] = useState<HistoryRun[]>([])
  const [loading, setLoading] = useState(true)
  const fetchRef = useRef(fetchHistory)
  // Before the load below: effects run in order.
  useEffect(() => { fetchRef.current = fetchHistory })

  const load = useCallback(async () => {
    try {
      const data = await fetchRef.current()
      setRuns(data.runs)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [])

  // Keyed on what the history is of; without a key, on the fetcher itself.
  const reloadOn = historyKey ?? fetchHistory
  useEffect(() => { load() }, [load, reloadOn])

  if (loading) {
    return (
      <div role="status" aria-live="polite" aria-label="Loading run history" style={{ display: 'flex', justifyContent: 'center', padding: 48, color: '#6b7280' }}>
        <Loader2 style={{ width: 20, height: 20, animation: 'spin 1s linear infinite' }} />
      </div>
    )
  }

  if (runs.length === 0) {
    return (
      <div style={{ padding: '48px 24px', textAlign: 'center', color: '#9ca3af', fontSize: 13 }}>
        No runs yet. Results will appear here after you run this {type}.
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 24px 8px' }}>
        <div role="status" aria-live="polite" style={{ fontSize: 12, color: '#6b7280', fontWeight: 500 }}>
          {runs.length} run{runs.length !== 1 ? 's' : ''}
        </div>
        <button
          type="button"
          onClick={() => {
            const url = URL.createObjectURL(new Blob([buildHistoryCSV(runs, type)], { type: 'text/csv' }))
            const a = document.createElement('a')
            a.href = url
            a.download = `${type}-run-history-${new Date().toISOString().slice(0, 10)}.csv`
            a.click()
            URL.revokeObjectURL(url)
          }}
          style={{
            display: 'flex', alignItems: 'center', gap: 4, padding: '4px 10px', fontSize: 12, fontWeight: 500,
            fontFamily: 'inherit', border: '1px solid #d1d5db', borderRadius: 6, backgroundColor: '#fff',
            color: '#374151', cursor: 'pointer',
          }}
        >
          <Download aria-hidden="true" style={{ width: 12, height: 12 }} />
          Export CSV
        </button>
      </div>
      {runs.map(run => (
        <RunRow key={run.id} run={run} type={type} />
      ))}
    </div>
  )
}
