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
  alreadyAppliedNote = '✓ Already applied automatically',
}: ApplyBackButtonProps) {
  return (
    <div style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
      <button
        onClick={onApply}
        disabled={!canApply || applying}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
          color: !canApply ? '#555' : '#fff',
          background: !canApply ? '#222' : 'linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)',
          border: '1px solid ' + (!canApply ? '#333' : '#7c3aed'),
          borderRadius: 6, cursor: !canApply || applying ? 'not-allowed' : 'pointer',
        }}
      >
        {applying ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Sparkles size={12} />}
        {applying ? applyingLabel : isAlreadyApplied ? applyAgainLabel : label}
      </button>
      {isAlreadyApplied && alreadyAppliedNote && (
        <span style={{ fontSize: 11, color: '#22c55e' }}>
          {alreadyAppliedNote}
        </span>
      )}
    </div>
  )
}
