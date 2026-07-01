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
        padding: '14px 16px',
        backgroundColor: 'rgba(239, 68, 68, 0.06)',
        border: '1px solid rgba(239, 68, 68, 0.25)',
        borderRadius: 6,
        display: 'flex', flexDirection: 'column', gap: 10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <AlertCircle size={16} style={{ color: '#fca5a5' }} />
          <div style={{ fontSize: 13, fontWeight: 600, color: '#fca5a5' }}>{message}</div>
        </div>
        <div style={{ fontSize: 12, color: '#aaa', lineHeight: 1.5 }}>{error}</div>
        <div style={{ display: 'flex', gap: 8 }}>
          {onRetry && (
            <button
              onClick={onRetry}
              style={btn('#7c3aed')}
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
      justifyContent: 'center', padding: '40px 16px', gap: 10,
    }}>
      <Loader2 aria-hidden="true" size={22} style={{ color: '#a78bfa', animation: 'spin 1s linear infinite' }} />
      <div style={{ fontSize: 13, fontWeight: 600, color: '#e5e5e5' }}>{message}</div>
      {sub && <div style={{ fontSize: 11, color: '#888' }}>{sub}</div>}
    </div>
  )
}

function btn(color?: string): React.CSSProperties {
  return {
    display: 'inline-flex', alignItems: 'center', gap: 4,
    padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
    color: '#e5e5e5',
    backgroundColor: color ?? '#2a2a2a',
    border: `1px solid ${color ?? '#3a3a3a'}`,
    borderRadius: 5, cursor: 'pointer',
  }
}
