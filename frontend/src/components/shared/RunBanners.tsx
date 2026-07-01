import { AlertCircle, Info, Sparkles } from 'lucide-react'

interface ErrorBannerProps {
  message: string
}

export function ErrorBanner({ message }: ErrorBannerProps) {
  return (
    <div role="alert" style={{
      padding: 10, marginBottom: 10, fontSize: 12,
      color: '#fca5a5', backgroundColor: 'rgba(239, 68, 68, 0.1)',
      border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: 6,
    }}>
      {message}
    </div>
  )
}

interface PastRunBannerProps {
  startedAt: string | null
  onExit: () => void
}

export function PastRunBanner({ startedAt, onExit }: PastRunBannerProps) {
  const when = startedAt ? new Date(startedAt).toLocaleString() : 'Unknown date'
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '8px 12px',
      backgroundColor: 'rgba(124, 58, 237, 0.10)',
      border: '1px solid rgba(124, 58, 237, 0.35)', borderRadius: 6,
      fontSize: 12, color: '#e5e5e5',
    }}>
      <Sparkles size={13} style={{ color: '#a78bfa', flexShrink: 0 }} />
      <span style={{ flex: 1 }}>
        Viewing past run from <b>{when}</b> — read-only.
      </span>
      <button
        onClick={onExit}
        style={{
          padding: '4px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
          color: '#e5e5e5', background: 'transparent',
          border: '1px solid rgba(124, 58, 237, 0.4)', borderRadius: 5,
          cursor: 'pointer',
        }}
      >
        Back to current
      </button>
    </div>
  )
}

interface FailedBannerProps {
  message: string
  onRunAgain: () => void
  title?: string
  retryLabel?: string
  /** Structured failure code from the backend (kb_not_found, test_set_too_small,
   * judge_unavailable, baselines_failed, budget_exhausted, unknown). When
   * provided, the banner renders a plain-English remediation block; the raw
   * ``message`` is shown collapsed underneath. Null/undefined for legacy runs. */
  errorCode?: string | null
}

// Plain-English remediation per classified error code. Edit this map to
// adjust banner copy without touching the component itself.
const REMEDIATIONS: Record<string, { what: string; how: string }> = {
  kb_not_found: {
    what: "We couldn't find this knowledge base.",
    how: 'It may have been deleted. Refresh the page and check the KB list.',
  },
  kb_empty: {
    what: "This KB doesn't have any indexed content yet.",
    how: 'Add at least one document or URL to the KB, wait for it to finish processing, then run Validate & improve again.',
  },
  test_set_too_small: {
    what: "There aren't enough test questions to tune against.",
    how: 'Open the Validate & improve wizard and add at least 5 questions with expected answers — auto-generation will fill in defaults if you skip this step.',
  },
  judge_unavailable: {
    what: 'No LLM judge model is configured for your account.',
    how: 'Ask your admin to enable at least one model in System Config → Models. The judge needs an answer-grading capable model (Sonnet / GPT-4 class).',
  },
  baselines_failed: {
    what: "Couldn't measure a baseline score before sweeping configs.",
    how: 'Usually a transient LLM/retrieval issue. Retry; if it keeps failing, check the KB for processing errors and verify your judge model is reachable.',
  },
  budget_exhausted: {
    what: 'The run ran out of token budget before completing trials.',
    how: 'Start a new run and pick a larger budget tier in Advanced settings — Standard or Thorough usually has enough headroom.',
  },
  unknown: {
    what: 'The run failed for an uncategorised reason.',
    how: 'Retry once — most transient LLM/network glitches clear up on retry. The raw error message is below.',
  },
}

export function FailedBanner({
  message, onRunAgain, title = 'Optimization failed', retryLabel = 'Try again',
  errorCode,
}: FailedBannerProps) {
  const remediation = errorCode ? REMEDIATIONS[errorCode] : null
  return (
    <div role="alert" style={{
      padding: 14, backgroundColor: 'rgba(239, 68, 68, 0.08)',
      border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <AlertCircle size={16} style={{ color: '#ef4444' }} />
        <span style={{ fontSize: 14, fontWeight: 600, color: '#fff' }}>{title}</span>
      </div>
      {remediation ? (
        <>
          <div style={{ fontSize: 12, color: '#fca5a5', marginBottom: 6 }}>
            {remediation.what}
          </div>
          <div style={{
            padding: '8px 10px', marginBottom: 10,
            fontSize: 12, color: '#e5e5e5', lineHeight: 1.5,
            backgroundColor: 'rgba(255,255,255,0.04)', border: '1px solid #2a2a2a',
            borderRadius: 6,
          }}>
            <strong style={{ color: '#fff' }}>What to do:</strong> {remediation.how}
          </div>
          <details style={{ marginBottom: 10 }}>
            <summary style={{ fontSize: 11, color: '#888', cursor: 'pointer' }}>
              Raw error message
            </summary>
            <div style={{ marginTop: 6, fontSize: 11, color: '#aaa', fontFamily: 'monospace' }}>
              {message}
            </div>
          </details>
        </>
      ) : (
        <div style={{ fontSize: 12, color: '#fca5a5', marginBottom: 10 }}>{message}</div>
      )}
      <button onClick={onRunAgain} style={{
        padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
        color: '#fff', backgroundColor: '#7c3aed',
        border: '1px solid #7c3aed', borderRadius: 6, cursor: 'pointer',
      }}>
        {retryLabel}
      </button>
    </div>
  )
}

interface CancelledBannerProps {
  completedTrials: number
  onRunAgain: () => void
  title?: string
  retryLabel?: string
}

export function CancelledBanner({ completedTrials, onRunAgain, title = 'Optimization cancelled', retryLabel = 'Run again' }: CancelledBannerProps) {
  return (
    <div role="status" style={{
      padding: 14, backgroundColor: '#1f1f1f',
      border: '1px solid #333', borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <Info size={16} style={{ color: '#888' }} />
        <span style={{ fontSize: 14, fontWeight: 600, color: '#fff' }}>{title}</span>
      </div>
      <div style={{ fontSize: 12, color: '#aaa', marginBottom: 10 }}>
        {completedTrials} trial{completedTrials !== 1 ? 's' : ''} completed before you cancelled.
      </div>
      <button onClick={onRunAgain} style={{
        padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
        color: '#fff', backgroundColor: '#7c3aed',
        border: '1px solid #7c3aed', borderRadius: 6, cursor: 'pointer',
      }}>
        {retryLabel}
      </button>
    </div>
  )
}
