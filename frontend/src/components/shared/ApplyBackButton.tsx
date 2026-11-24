import { Loader2, Sparkles } from 'lucide-react'

interface ApplyBackButtonProps {
  /** Whether the current user has permission to apply. */
  canApply: boolean
  onApply: () => void
  applying: boolean
  /** Whether this exact config is already applied — labels button as "Apply again". */
  isAlreadyApplied: boolean
  /** Default: "Apply optimized settings". */
  label?: string
  /** Default: "Apply again". */
  applyAgainLabel?: string
  /** Default: "Applying…". */
  applyingLabel?: string
  /** Default: "✓ Already applied automatically". Set null to hide. */
  alreadyAppliedNote?: string | null
}

export function ApplyBackButton({
  canApply, onApply, applying, isAlreadyApplied,
  label = 'Apply optimized settings',
  applyAgainLabel = 'Apply again',
  applyingLabel = 'Applying…',
  alreadyAppliedNote = 'These settings are applied',
}: ApplyBackButtonProps) {
  return (
    <div style={{ marginTop: 'var(--workspace-space-12)', display: 'flex', gap: 'var(--workspace-space-8)', alignItems: 'center', flexWrap: 'wrap' }}>
      <button
        onClick={onApply}
        disabled={!canApply || applying}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-6)',
          padding: "var(--workspace-space-6) var(--workspace-space-16)", fontSize: 'var(--workspace-font-meta)', fontWeight: 600, fontFamily: 'inherit',
          color: !canApply ? 'var(--workspace-muted)' : 'var(--highlight-text-color, #000)',
          background: !canApply ? 'var(--workspace-surface)' : 'var(--highlight-color, #eab308)',
          border: '1px solid ' + (!canApply ? 'var(--workspace-border)' : 'var(--highlight-color, #eab308)'),
          borderRadius: 'var(--workspace-radius-small)', cursor: !canApply || applying ? 'not-allowed' : 'pointer',
        }}
      >
        {applying ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Sparkles size={12} />}
        {applying ? applyingLabel : isAlreadyApplied ? applyAgainLabel : label}
      </button>
      {isAlreadyApplied && alreadyAppliedNote && (
        <span style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-success)' }}>
          {alreadyAppliedNote}
        </span>
      )}
    </div>
  )
}
