import type { RunHistoryEntry } from '../../api/workflows'
import { formatLocalTimestamp } from '../../utils/time'

export function WorkflowLastRunNotice({ run, error, onShow, onRetry }: {
  run: RunHistoryEntry | null
  error: string | null
  onShow: (sessionId: string) => void
  onRetry: () => void
}) {
  if (!run?.session_id && !error) return null
  const status = run?.pending_review_uuid ? 'Awaiting approval'
    : ({ completed: 'Completed', failed: 'Failed', error: 'Failed', running: 'In progress', queued: 'Queued', canceled: 'Canceled' }[run?.status ?? ''] ?? run?.status)
  return <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-6 py-3 text-sm">
    {run?.session_id ? <>
      <p>Your last run: {status}{run.started_at ? ` · ${formatLocalTimestamp(run.started_at)}` : ''}</p>
      <button type="button" className="page-button" onClick={() => onShow(run.session_id!)}>Show last run</button>
    </> : <>
      <p role="alert">{error}</p>
      <button type="button" className="page-button" onClick={onRetry}>Retry last run</button>
    </>}
  </div>
}
