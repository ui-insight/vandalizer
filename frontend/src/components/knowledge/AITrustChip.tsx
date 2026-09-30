import { TrendingUp, ShieldQuestion, Minus } from 'lucide-react'
import type { KnowledgeBase } from '../../types/knowledge'

interface Props {
  /** With-KB accuracy from the latest validation run (0–1). */
  score?: number | null
  /** No-KB baseline accuracy (0–1). */
  baseline?: number | null
  /** Lift = score − baseline (0–1). */
  lift?: number | null
  /** Visual size. "sm" for cards, "md" for header rows. */
  size?: 'sm' | 'md'
  metric?: KnowledgeBase['last_validation_metric']
  configState?: KnowledgeBase['last_validation_config_state']
}

/**
 * Plain-language signal of how much more accurate the AI becomes when it has
 * this KB to consult, compared to answering from its training data alone.
 *
 * KBs exist primarily to build trust in the AI's answers — this chip is the
 * one-glance summary of that trust for users who don't know what RAG is.
 */
export function AITrustChip({ score, baseline, lift, size = 'sm', metric, configState }: Props) {
  const composite = metric === 'composite_quality'
  const hasRun = lift != null || score != null
  const measuredLift = composite ? null : lift ?? (score != null && baseline != null ? score - baseline : null)
  const liftPts = measuredLift != null ? Math.round(measuredLift * 100) : null
  const fontSize = size === 'sm' ? 12 : 13
  const iconSize = size === 'sm' ? 12 : 14
  const padY = size === 'sm' ? 2 : 4
  const padX = size === 'sm' ? 8 : 10

  if (score != null && (composite || liftPts == null)) {
    return (
      <span
        title={composite
          ? 'Composite retrieval and answer quality on tested questions. This is not an answer-accuracy comparison with AI alone.'
          : 'Answer accuracy on tested questions; no AI-only comparison was recorded.'}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: `${padY}px ${padX}px`, borderRadius: 10, fontSize, fontWeight: 600, color: 'var(--workspace-muted)', backgroundColor: 'var(--workspace-canvas)', border: '1px solid var(--workspace-border)' }}
      >
        <Minus size={iconSize} style={{ flexShrink: 0 }} />
        {composite
          ? `Quality ${Math.round(score * 100)}/100 · ${configState === 'applied' ? 'applied in run' : configState === 'reverted' ? 'application reverted' : configState === 'default' ? 'default tested' : 'proposed'}`
          : `Answer accuracy ${Math.round(score * 100)}%`}
      </span>
    )
  }

  if (!hasRun) {
    return (
      <span
        title="No validation has been run on this knowledge base yet, so we can't show how much it improves AI accuracy. Click into the KB and run validation to find out."
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 4,
          padding: `${padY}px ${padX}px`, borderRadius: 999,
          fontSize, fontWeight: 600,
          color: 'var(--workspace-warning)',
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
          color: 'var(--workspace-success)',
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
        color: 'var(--workspace-muted)',
        backgroundColor: 'var(--workspace-canvas)',
        border: '1px solid var(--workspace-border)',
      }}
    >
      <Minus size={iconSize} />
      No measured improvement
    </span>
  )
}
