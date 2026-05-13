import { TrendingUp, ShieldQuestion, Minus } from 'lucide-react'

interface Props {
  /** With-KB accuracy from the latest validation run (0–1). */
  score?: number | null
  /** No-KB baseline accuracy (0–1). */
  baseline?: number | null
  /** Lift = score − baseline (0–1). */
  lift?: number | null
  /** Visual size. "sm" for cards, "md" for header rows. */
  size?: 'sm' | 'md'
}

/**
 * Plain-language signal of how much more accurate the AI becomes when it has
 * this KB to consult, compared to answering from its training data alone.
 *
 * KBs exist primarily to build trust in the AI's answers — this chip is the
 * one-glance summary of that trust for users who don't know what RAG is.
 */
export function AITrustChip({ score, baseline, lift, size = 'sm' }: Props) {
  const hasRun = lift != null || (score != null && baseline != null)
  const liftPts = lift != null ? Math.round(lift * 100) : null
  const fontSize = size === 'sm' ? 11 : 13
  const iconSize = size === 'sm' ? 12 : 14
  const padY = size === 'sm' ? 2 : 4
  const padX = size === 'sm' ? 8 : 10

  if (!hasRun) {
    return (
      <span
        title="No validation has been run on this knowledge base yet, so we can't show how much it improves AI accuracy. Click into the KB and run validation to find out."
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 4,
          padding: `${padY}px ${padX}px`, borderRadius: 999,
          fontSize, fontWeight: 600,
          color: '#fbbf24',
          backgroundColor: 'rgba(251, 191, 36, 0.1)',
          border: '1px solid rgba(251, 191, 36, 0.3)',
        }}
      >
        <ShieldQuestion size={iconSize} />
        Not yet validated
      </span>
    )
  }

  if (liftPts != null && liftPts > 0) {
    return (
      <span
        title={
          score != null && baseline != null
            ? `With this KB, the AI is ${Math.round(score * 100)}% accurate on your test questions; without it, only ${Math.round(baseline * 100)}%.`
            : 'The AI answers more accurately with this KB than without.'
        }
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 4,
          padding: `${padY}px ${padX}px`, borderRadius: 999,
          fontSize, fontWeight: 600,
          color: '#22c55e',
          backgroundColor: 'rgba(34, 197, 94, 0.12)',
          border: '1px solid rgba(34, 197, 94, 0.3)',
        }}
      >
        <TrendingUp size={iconSize} />
        +{liftPts} pts vs AI alone
      </span>
    )
  }

  // Lift is zero or negative — the KB didn't help (or hurt).
  return (
    <span
      title={
        score != null && baseline != null
          ? `With this KB, the AI is ${Math.round(score * 100)}% accurate; without it, ${Math.round(baseline * 100)}%. The AI didn't measurably benefit from the KB on these questions.`
          : 'The AI did not answer more accurately with this KB than without.'
      }
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        padding: `${padY}px ${padX}px`, borderRadius: 999,
        fontSize, fontWeight: 600,
        color: '#9ca3af',
        backgroundColor: 'rgba(255,255,255,0.06)',
        border: '1px solid rgba(255,255,255,0.1)',
      }}
    >
      <Minus size={iconSize} />
      No measured improvement
    </span>
  )
}
