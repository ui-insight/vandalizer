import { TrendingUp, ShieldQuestion, Minus } from 'lucide-react'

interface Props {
  /** With-KB accuracy from the latest validation run (0–1). */
  score?: number | null
  /** No-KB baseline accuracy (0–1). */
  baseline?: number | null
  /** Lift = score − baseline (0–1). */
  lift?: number | null
  /** ISO timestamp of the latest validation run. */
  validatedAt?: string | null
}

function formatRelativeTime(iso: string | null | undefined): string | null {
  if (!iso) return null
  const ts = Date.parse(iso)
  if (Number.isNaN(ts)) return null
  const diffSec = Math.max(0, (Date.now() - ts) / 1000)
  if (diffSec < 60) return 'just now'
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`
  if (diffSec < 86400 * 30) return `${Math.floor(diffSec / 86400)}d ago`
  return new Date(ts).toLocaleDateString()
}

/**
 * Headline banner for the KB detail view that answers, in plain language:
 * "does the AI actually answer my questions better when it has this KB?"
 *
 * KBs are a trust mechanism — this banner is the proof. When unvalidated,
 * the banner prompts the owner to run validation so they (and their team)
 * can see whether the KB is pulling its weight.
 */
export function KBTrustBanner({ score, baseline, lift, validatedAt }: Props) {
  const hasRun = lift != null || (score != null && baseline != null)
  const liftPts = lift != null ? Math.round(lift * 100) : null
  const scorePct = score != null ? Math.round(score * 100) : null
  const baselinePct = baseline != null ? Math.round(baseline * 100) : null
  const relTime = formatRelativeTime(validatedAt)

  const positive = hasRun && liftPts != null && liftPts > 0

  let accent = '#9ca3af'
  let bg = 'rgba(255,255,255,0.04)'
  let border = 'rgba(255,255,255,0.08)'
  let Icon = Minus

  if (!hasRun) {
    accent = '#fbbf24'
    bg = 'rgba(251, 191, 36, 0.08)'
    border = 'rgba(251, 191, 36, 0.25)'
    Icon = ShieldQuestion
  } else if (positive) {
    accent = '#22c55e'
    bg = 'rgba(34, 197, 94, 0.08)'
    border = 'rgba(34, 197, 94, 0.3)'
    Icon = TrendingUp
  }

  return (
    <div
      style={{
        display: 'flex', gap: 14, alignItems: 'flex-start',
        padding: '12px 14px', borderRadius: 10,
        backgroundColor: bg, border: `1px solid ${border}`,
        marginBottom: 16,
      }}
    >
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        width: 36, height: 36, borderRadius: 10,
        backgroundColor: 'rgba(255,255,255,0.05)', color: accent, flexShrink: 0,
      }}>
        <Icon size={18} />
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 10, fontWeight: 700, color: '#9ca3af',
          textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 2,
        }}>
          AI Trust
        </div>

        {!hasRun ? (
          <>
            <div style={{ fontSize: 14, fontWeight: 600, color: '#e5e5e5', marginBottom: 4 }}>
              AI accuracy not yet measured
            </div>
            <div style={{ fontSize: 12, color: '#9ca3af', lineHeight: 1.5 }}>
              Run validation below to see how much more accurate the AI is at answering
              questions about this material when it can read the KB, compared to answering
              from training data alone.
            </div>
          </>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap', marginBottom: 4 }}>
              {liftPts != null && (
                <span style={{ fontSize: 22, fontWeight: 700, color: accent }}>
                  {liftPts > 0 ? '+' : ''}{liftPts} pts
                </span>
              )}
              <span style={{ fontSize: 13, color: '#cbd5e1' }}>
                {positive
                  ? 'more accurate than asking the AI alone'
                  : 'no measured improvement over the AI alone'}
              </span>
            </div>
            <div style={{ fontSize: 12, color: '#9ca3af', lineHeight: 1.5 }}>
              {scorePct != null && baselinePct != null ? (
                <>
                  The AI answered {scorePct}% of the test questions correctly with this KB,
                  versus {baselinePct}% without it.
                </>
              ) : scorePct != null ? (
                <>The AI answered {scorePct}% of the test questions correctly with this KB.</>
              ) : null}
              {relTime && (
                <span style={{ color: '#666' }}> · Last validated {relTime}</span>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
