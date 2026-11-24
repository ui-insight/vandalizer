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

/** Summarize measured evidence without turning a test score into a guarantee. */
export function AITrustChip({ score, baseline, lift, size = 'sm', metric, configState }: Props) {
  const composite = metric === 'composite_quality'
  const measuredLift = composite ? null : lift ?? (score != null && baseline != null ? score - baseline : null)
  const hasRun = score != null || measuredLift != null
  const positive = measuredLift != null && measuredLift > 0
  const label = !hasRun ? 'Not evaluated' : composite || measuredLift == null ? 'Evaluation recorded'
    : positive ? 'Improved on tested questions' : 'No measured improvement'
  const Icon = !hasRun ? ShieldQuestion : positive ? TrendingUp : Minus
  const provenance = configState === 'applied' ? 'applied in run' : configState === 'reverted' ? 'application reverted'
    : configState === 'default' ? 'default tested' : configState === 'no_improvement' ? 'no improvement found' : 'proposed'

  return (
    <details onClick={event => event.stopPropagation()} style={{ fontSize: size === 'sm' ? 'var(--workspace-font-meta)' : 'var(--workspace-font-control)', color: 'var(--workspace-muted)' }}>
      <summary style={{ cursor: 'pointer', padding: '4px 8px', borderRadius: 'var(--workspace-radius-medium)', backgroundColor: 'var(--workspace-canvas)', border: '1px solid var(--workspace-border)' }}>
        <Icon size={12} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
        {label}{composite && hasRun ? ` · ${provenance}` : ''}
      </summary>
      <div style={{ padding: 8 }}>
        {score != null && <div>{composite ? 'Composite quality' : 'Answer accuracy'}: {Math.round(score * 100)}{composite ? '/100' : '%'}</div>}
        {!composite && baseline != null && <div>AI-only baseline: {Math.round(baseline * 100)}%</div>}
        {measuredLift != null && <div>Difference: {Math.round(measuredLift * 100)} pts on tested questions</div>}
        <div>{hasRun ? 'These results describe the tested questions. Open the evaluation to review sample size, failures, and coverage.' : 'Test representative questions to measure this knowledge base.'}</div>
      </div>
    </details>
  )
}
