import { AlertTriangle, RefreshCw } from 'lucide-react'

/**
 * Stale-plan warning for the Validate tab — the workflow was edited after the
 * validation plan was generated/saved, so checks may reference steps or fields
 * that no longer exist. That shows up as SKIP verdicts and unfairly low grades,
 * which look like a bad workflow but aren't.
 *
 * Action buttons are manage-gated; view-only users see the explanation only.
 */
export function StalePlanBanner({
  orphanedCount,
  canManage,
  generating,
  confirming,
  onRegenerate,
  onConfirmFresh,
}: {
  orphanedCount: number
  canManage: boolean
  generating: boolean
  confirming: boolean
  onRegenerate: () => void
  onConfirmFresh: () => void
}) {
  return (
    <div
      data-testid="stale-plan-banner"
      style={{
        display: 'flex', alignItems: 'flex-start', gap: 10,
        padding: '10px 12px', marginBottom: 8,
        backgroundColor: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 6,
      }}
    >
      <AlertTriangle style={{ width: 15, height: 15, color: '#d97706', flexShrink: 0, marginTop: 1 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: '#92400e' }}>
          This plan may be out of sync with the workflow
        </div>
        <div style={{ fontSize: 11, color: '#a16207', marginTop: 2, lineHeight: 1.4 }}>
          {orphanedCount > 0
            ? `${orphanedCount} check${orphanedCount === 1 ? '' : 's'} target${orphanedCount === 1 ? 's' : ''} a step that no longer exists. `
            : 'The workflow was edited after this plan was created. '}
          Stale checks skip or fail unfairly, dragging the grade down even when the workflow is fine.
        </div>
        {canManage && (
          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            <button
              onClick={onRegenerate}
              disabled={generating}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '4px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
                borderRadius: 5, border: 'none', backgroundColor: '#d97706', color: '#fff',
                cursor: generating ? 'not-allowed' : 'pointer', opacity: generating ? 0.6 : 1,
              }}
            >
              <RefreshCw style={{ width: 11, height: 11 }} /> Regenerate plan
            </button>
            <button
              onClick={onConfirmFresh}
              disabled={confirming}
              title="Keep the plan as-is and stop warning until the workflow changes again"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '4px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
                borderRadius: 5, border: '1px solid #fcd34d', backgroundColor: '#fff',
                color: '#92400e', cursor: confirming ? 'wait' : 'pointer',
                opacity: confirming ? 0.6 : 1,
              }}
            >
              Plan is still correct
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
