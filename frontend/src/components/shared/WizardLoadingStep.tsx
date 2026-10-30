import { Loader2, AlertCircle, RotateCcw } from 'lucide-react'

interface Props {
  message: string
  sub?: string
  error?: string | null
  onRetry?: () => void
  /** Optional secondary action — used to let the user skip the step on error. */
  onSkip?: () => void
  skipLabel?: string
}

/** Shared spinner/status/error pane for async wizard steps. Renders a centered
 * spinner while loading, or a friendly error block with retry/skip when the
 * caller passes ``error``. Used by PreviewStep (test-set generation) and
 * BaselineStep (no-KB probe). */
export function WizardLoadingStep({ message, sub, error, onRetry, onSkip, skipLabel }: Props) {
  if (error) {
    return (
      <div role="alert" style={{
        padding: "var(--workspace-space-16) var(--workspace-space-16)",
        backgroundColor: 'rgba(239, 68, 68, 0.06)',
        border: '1px solid rgba(239, 68, 68, 0.25)',
        borderRadius: 'var(--workspace-radius-small)',
        display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-12)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)' }}>
          <AlertCircle size={16} style={{ color: 'var(--workspace-danger)' }} />
          <div style={{ fontSize: 'var(--workspace-font-control)', fontWeight: 600, color: 'var(--workspace-danger)' }}>{message}</div>
        </div>
        <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', lineHeight: 1.5 }}>{error}</div>
        <div style={{ display: 'flex', gap: 'var(--workspace-space-8)' }}>
          {onRetry && (
            <button
              onClick={onRetry}
              style={btn('var(--workspace-info)')}
            >
              <RotateCcw size={12} />
              Retry
            </button>
          )}
          {onSkip && (
            <button
              onClick={onSkip}
              style={btn()}
            >
              {skipLabel || 'Skip'}
            </button>
          )}
        </div>
      </div>
    )
  }
  return (
    <div role="status" aria-live="polite" style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', padding: "40px var(--workspace-space-16)", gap: 'var(--workspace-space-12)',
    }}>
      <Loader2 aria-hidden="true" size={22} style={{ color: 'var(--workspace-info)', animation: 'spin 1s linear infinite' }} />
      <div style={{ fontSize: 'var(--workspace-font-control)', fontWeight: 600, color: 'var(--workspace-text)' }}>{message}</div>
      {sub && <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>{sub}</div>}
    </div>
  )
}

function btn(color?: string): React.CSSProperties {
  return {
    display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)',
    padding: "var(--workspace-space-6) var(--workspace-space-12)", fontSize: 'var(--workspace-font-meta)', fontWeight: 600, fontFamily: 'inherit',
    color: 'var(--workspace-text)',
    backgroundColor: color ?? 'var(--workspace-surface)',
    border: `1px solid ${color ?? 'var(--workspace-border)'}`,
    borderRadius: 'var(--workspace-radius-small)', cursor: 'pointer',
  }
}
