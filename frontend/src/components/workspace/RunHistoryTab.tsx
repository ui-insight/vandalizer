import { Link } from '@tanstack/react-router'
import { useCallback, useRef, useState } from 'react'
import { useAdminQuery } from '../admin/shared/useAdminQuery'
import { CheckCircle, XCircle, Loader2, Clock, FileText, ChevronDown, ChevronRight, Zap, Download, ClipboardCheck } from 'lucide-react'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { relativeTime } from '../../utils/time'
import { getWorkflowStatus, downloadResults } from '../../api/workflows'
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
  return <Clock style={{ width: 14, height: 14, color: 'var(--ui-text-muted, #59616b)', flexShrink: 0 }} />
}

function ResultPreview({ snapshot, type }: { snapshot: Record<string, unknown>; type: 'workflow' | 'extraction' }) {
  if (!snapshot || Object.keys(snapshot).length === 0) return null

  if (type === 'extraction') {
    const normalized = snapshot.normalized as Record<string, unknown> | undefined
    if (!normalized || Object.keys(normalized).length === 0) return null
    const entries = Object.entries(normalized)
    return (
      <div style={{ marginTop: 'var(--workspace-space-8)', fontSize: 'var(--workspace-font-meta)', color: '#374151' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <tbody>
            {entries.map(([key, val]) => (
              <tr key={key}>
                <td style={{ padding: "var(--workspace-space-4) var(--workspace-space-8) var(--workspace-space-4) 0", color: '#6b7280', fontWeight: 500, verticalAlign: 'top', wordBreak: 'break-word' }}>{key}</td>
                <td style={{ padding: "var(--workspace-space-4) 0", wordBreak: 'break-word' }}>{val != null ? String(val) : <span style={{ color: '#6b7280' }}>No value</span>}</td>
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
    <div style={{ marginTop: 'var(--workspace-space-8)', fontSize: 'var(--workspace-font-meta)', color: '#6b7280' }}>
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
  const request = useCallback(() => getWorkflowStatus(sessionId), [sessionId])
  const { data: status, loading, error, load } = useAdminQuery(request)
  const [showDownload, setShowDownload] = useState(false)
  const downloadButton = useRef<HTMLButtonElement>(null)
  const finalOutput = status?.final_output as Record<string, unknown> | null
  const output = finalOutput && typeof finalOutput === 'object' && 'output' in finalOutput ? finalOutput.output : finalOutput

  if (loading) {
    return (
      <div role="status" aria-label="Loading run output" style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-6)', marginTop: 'var(--workspace-space-8)', fontSize: 'var(--workspace-font-meta)', color: '#6b7280' }}>
        <Loader2 style={{ width: 12, height: 12, animation: 'spin 1s linear infinite' }} />
        Loading output...
      </div>
    )
  }

  if (error) return <div role="alert" className="mt-2 text-sm text-red-800">{error} <button type="button" onClick={load} className="underline">Retry run output</button></div>

  if (output == null) {
    return (
      <div style={{ marginTop: 'var(--workspace-space-8)', fontSize: 'var(--workspace-font-meta)', color: 'var(--ui-text-muted, #59616b)' }}>
        No final output was saved for this run.
      </div>
    )
  }

  const file = summarizeFilePayload(output)
  return (
    <div style={{ marginTop: 'var(--workspace-space-8)' }}>
      {file ? (
        <FileOutputCard summary={file} downloadHref={downloadResults(sessionId, 'text')} maxHeight="50vh" />
      ) : (
        <div
          role="region" aria-label="Saved workflow output" tabIndex={0}
          className="chat-markdown"
          style={{
            backgroundColor: '#f9fafb', border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)',
            padding: 'var(--workspace-space-12)', fontSize: 'var(--workspace-font-control)', lineHeight: 1.6,
            maxHeight: '50vh', overflowY: 'auto', overflowX: 'auto',
            color: '#374151', wordBreak: 'break-word',
          }}
          dangerouslySetInnerHTML={{ __html: renderMarkdownOutput(output) }}
        />
      )}
      <div onKeyDown={event => { if (event.key === 'Escape') { setShowDownload(false); downloadButton.current?.focus() } }} style={{ marginTop: 'var(--workspace-space-8)' }}>
        <button
          ref={downloadButton}
          onClick={() => setShowDownload(s => !s)}
          aria-expanded={showDownload}
          style={{
            display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-6)', padding: "var(--workspace-space-6) var(--workspace-space-12)",
            fontSize: 'var(--workspace-font-meta)', fontWeight: 600, fontFamily: 'inherit',
            border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-small)',
            backgroundColor: '#fff', cursor: 'pointer', color: '#374151',
          }}
        >
          <Download style={{ width: 12, height: 12 }} />
          Download
        </button>
        {showDownload && (
          <div style={{
            marginTop: 'var(--workspace-space-4)', maxHeight: '45vh', overflowY: 'auto',
            backgroundColor: '#fff', border: "1px solid var(--workspace-border)", borderRadius: 'var(--workspace-radius-medium)',
            boxShadow: '0 8px 24px rgba(0,0,0,0.12)', minWidth: 0, width: '100%', maxWidth: 320,
            padding: "var(--workspace-space-4) 0",
          }}>
            {DOWNLOAD_FORMATS.map(({ fmt, label, desc, parseStructured }) => (
              <a
                key={label}
                href={downloadResults(sessionId, fmt, { parseStructured })}
                onClick={() => setShowDownload(false)}
                style={{
                  display: 'flex', flexDirection: 'column', gap: 1,
                  padding: "var(--workspace-space-8) var(--workspace-space-16)", fontSize: 'var(--workspace-font-control)', fontWeight: 500,
                  color: '#374151', textDecoration: 'none',
                  transition: 'background-color 0.1s',
                }}
                onMouseEnter={e => { e.currentTarget.style.backgroundColor = '#f3f4f6' }}
                onMouseLeave={e => { e.currentTarget.style.backgroundColor = '#fff' }}
              >
                <span>{label}</span>
                <span style={{ fontSize: 'var(--workspace-font-meta)', color: '#6b7280', fontWeight: 400 }}>{desc}</span>
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
  const hasResults = hasSnapshot || canFetchOutput

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
          gap: 'var(--workspace-space-12)',
          padding: "var(--workspace-space-12) var(--workspace-space-24)",
          background: 'none',
          border: 'none',
          cursor: hasResults ? 'pointer' : 'default',
          fontFamily: 'inherit',
          textAlign: 'left',
        }}
      >
        <StatusIcon status={displayStatus} />

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 'var(--workspace-space-8)' }}>
            <span style={{ fontSize: 'var(--workspace-font-control)', fontWeight: 500, color: '#202124' }}>
              {run.started_at ? relativeTime(run.started_at) : 'Unknown'}
            </span>
            <span style={{
              fontSize: 'var(--workspace-font-meta)',
              fontWeight: 500,
              padding: "1px var(--workspace-space-6)",
              borderRadius: 'var(--workspace-radius-small)',
              backgroundColor: reviewUuid ? '#fef3c7' : run.status === 'completed' ? '#dcfce7' : run.status === 'failed' || run.status === 'error' ? '#fef2f2' : '#f3f4f6',
              color: reviewUuid ? '#92400e' : run.status === 'completed' ? '#166534' : run.status === 'failed' || run.status === 'error' ? '#991b1b' : '#6b7280',
            }}>
              {displayStatus}
            </span>
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--workspace-space-12)', marginTop: 'var(--workspace-space-4)', fontSize: 'var(--workspace-font-meta)', color: '#6b7280' }}>
            {run.duration_ms != null && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-4)' }}>
                <Clock style={{ width: 11, height: 11 }} />
                {formatDuration(run.duration_ms)}
              </span>
            )}
            {run.documents_touched > 0 && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-4)' }}>
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
              <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-4)' }}>
                <Zap style={{ width: 11, height: 11 }} />
                {(run.tokens_input + run.tokens_output).toLocaleString()} tokens
              </span>
            )}
          </div>

          {run.error && (
            <div style={{ fontSize: 'var(--workspace-font-meta)', color: '#dc2626', marginTop: 'var(--workspace-space-4)' }}>
              {run.error}
            </div>
          )}
        </div>

        {hasResults && (
          expanded
            ? <ChevronDown style={{ width: 14, height: 14, color: 'var(--ui-text-muted, #59616b)', flexShrink: 0 }} />
            : <ChevronRight style={{ width: 14, height: 14, color: 'var(--ui-text-muted, #59616b)', flexShrink: 0 }} />
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
            fontSize: 'var(--workspace-font-meta)', fontWeight: 600, color: '#0369a1', textDecoration: 'underline',
          }}
        >
          Open review →
        </Link>
      )}

      {expanded && hasResults && (
        <div style={{ padding: "0 var(--workspace-space-24) var(--workspace-space-12) 48px" }}>
          {canFetchOutput
            ? <WorkflowRunOutput sessionId={run.session_id!} />
            : <ResultPreview snapshot={run.result_snapshot} type={type} />}
        </div>
      )}
    </div>
  )
}

export function RunHistoryTab({
  fetchHistory,
  type,
}: {
  fetchHistory: () => Promise<{ runs: HistoryRun[] }>
  type: 'workflow' | 'extraction'
}) {
  const { data, loading, error, load } = useAdminQuery(fetchHistory)
  const runs = data?.runs ?? []

  if (loading) {
    return (
      <div role="status" aria-live="polite" aria-label="Loading run history" style={{ display: 'flex', justifyContent: 'center', padding: 48, color: '#6b7280' }}>
        <Loader2 style={{ width: 20, height: 20, animation: 'spin 1s linear infinite' }} />
      </div>
    )
  }

  if (error) return <div role="alert" className="p-6 text-sm text-red-800">{error} <button type="button" onClick={load} className="underline">Retry run history</button></div>

  if (runs.length === 0) {
    return (
      <div style={{ padding: "48px var(--workspace-space-24)", textAlign: 'center', color: 'var(--ui-text-muted, #59616b)', fontSize: 'var(--workspace-font-control)' }}>
        No runs yet. Results will appear here after you run this {type}.
      </div>
    )
  }

  return (
    <div>
      <div role="status" aria-live="polite" style={{ padding: "var(--workspace-space-12) var(--workspace-space-24) var(--workspace-space-8)", fontSize: 'var(--workspace-font-meta)', color: '#6b7280', fontWeight: 500 }}>
        {runs.length} run{runs.length !== 1 ? 's' : ''}
      </div>
      {runs.map(run => (
        <RunRow key={run.id} run={run} type={type} />
      ))}
    </div>
  )
}
