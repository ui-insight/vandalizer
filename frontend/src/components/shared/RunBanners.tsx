import { AlertCircle, Info, Sparkles } from 'lucide-react'

/**
 * Banner palettes.
 *
 * These banners were written against a dark surface: a translucent tint for
 * the background and near-white text on top of it. Rendered on the light
 * panels they actually live on — the extraction and knowledge-base Validate
 * tabs — the tint washed out to pale pink and the text all but vanished
 * ("Optimization failed — No extraction fields defined" was unreadable, the
 * support ticket behind this). The banners are handed around and dropped into
 * whatever container a caller has, so they cannot borrow a background: each
 * one paints an opaque surface of its own and puts text on it that meets
 * WCAG AA (≥ 4.5:1) against that surface, wherever it is rendered. The values
 * are the app's existing light-theme alert colors (see ToastContext).
 */
const RED = {
  surface: '#fef2f2',
  border: '#fecaca',
  strong: '#991b1b',
  text: '#b91c1c',
  icon: '#dc2626',
}

const VIOLET = {
  surface: '#f5f3ff',
  border: '#ddd6fe',
  text: '#5b21b6',
  icon: '#7c3aed',
}

const NEUTRAL = {
  surface: '#f9fafb',
  border: '#e5e7eb',
  strong: '#111827',
  text: '#4b5563',
  // Quiet, but still AA against the red surface it sits on in FailedBanner —
  // #6b7280 lands at 4.42:1 there, just under.
  muted: '#5b6472',
}

interface ErrorBannerProps {
  message: string
}

export function ErrorBanner({ message }: ErrorBannerProps) {
  return (
    <div role="alert" style={{
      padding: 10, marginBottom: 10, fontSize: 12,
      color: RED.text, backgroundColor: RED.surface,
      border: `1px solid ${RED.border}`, borderRadius: 6,
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
      backgroundColor: VIOLET.surface,
      border: `1px solid ${VIOLET.border}`, borderRadius: 6,
      fontSize: 12, color: VIOLET.text,
    }}>
      <Sparkles size={13} style={{ color: VIOLET.icon, flexShrink: 0 }} />
      <span style={{ flex: 1 }}>
        Viewing past run from <b>{when}</b> (read-only).
      </span>
      <button
        onClick={onExit}
        style={{
          padding: '4px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
          color: VIOLET.text, background: '#fff',
          border: `1px solid ${VIOLET.border}`, borderRadius: 5,
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
    how: 'Open the Validate & improve wizard and add at least 5 questions with expected answers. Auto-generation will fill in defaults if you skip this step.',
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
    how: 'Start a new run and pick a larger budget tier in Advanced settings. Standard or Thorough usually has enough headroom.',
  },
  unknown: {
    what: 'The run failed for an uncategorised reason.',
    how: 'Retry once: most transient LLM/network glitches clear up on retry. The raw error message is below.',
  },
}

export function FailedBanner({
  message, onRunAgain, title = 'Optimization failed', retryLabel = 'Try again',
  errorCode,
}: FailedBannerProps) {
  const remediation = errorCode ? REMEDIATIONS[errorCode] : null
  return (
    <div role="alert" style={{
      padding: 14, backgroundColor: RED.surface,
      border: `1px solid ${RED.border}`, borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <AlertCircle size={16} style={{ color: RED.icon }} />
        <span style={{ fontSize: 14, fontWeight: 600, color: RED.strong }}>{title}</span>
      </div>
      {remediation ? (
        <>
          <div style={{ fontSize: 12, color: RED.text, marginBottom: 6 }}>
            {remediation.what}
          </div>
          <div style={{
            padding: '8px 10px', marginBottom: 10,
            fontSize: 12, color: NEUTRAL.text, lineHeight: 1.5,
            backgroundColor: '#fff', border: `1px solid ${RED.border}`,
            borderRadius: 6,
          }}>
            <strong style={{ color: NEUTRAL.strong }}>What to do:</strong> {remediation.how}
          </div>
          <details style={{ marginBottom: 10 }}>
            <summary style={{ fontSize: 11, color: NEUTRAL.muted, cursor: 'pointer' }}>
              Raw error message
            </summary>
            <div style={{ marginTop: 6, fontSize: 11, color: NEUTRAL.text, fontFamily: 'monospace' }}>
              {message}
            </div>
          </details>
        </>
      ) : (
        <div style={{ fontSize: 12, color: RED.text, marginBottom: 10 }}>{message}</div>
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
      padding: 14, backgroundColor: NEUTRAL.surface,
      border: `1px solid ${NEUTRAL.border}`, borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <Info size={16} style={{ color: NEUTRAL.muted }} />
        <span style={{ fontSize: 14, fontWeight: 600, color: NEUTRAL.strong }}>{title}</span>
      </div>
      <div style={{ fontSize: 12, color: NEUTRAL.text, marginBottom: 10 }}>
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
