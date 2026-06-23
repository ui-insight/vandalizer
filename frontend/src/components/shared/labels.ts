/**
 * Per-domain copy for the three Autovalidate surfaces (KB / Extraction /
 * Workflow). Centralized so the next time the wording shifts it doesn't drift
 * three ways.
 *
 * The tile trio standardizes to **No baseline / Your settings / Tuned**
 * everywhere — what the "no baseline" means differs per domain (no retrieval,
 * no extraction config, no workflow at all), and we explain that in the
 * score-floor descriptions rather than the tile label.
 */

export type AutovalidateDomain = 'kb' | 'extraction' | 'workflow'

export interface DomainLabels {
  /** Trio used in QualityComparisonCard + ScoreTile rows. */
  baselineTile: { noBaseline: string; yourSettings: string; tuned: string }
  /** Copy for the live-progress score floor (used by OptimizationProgressCard). */
  scoreFloorLabel: string
  scoreFloorDescription: string
  /** Suffix on the lift number ("better than no baseline"). */
  liftLabel: string
}

const COMMON_TILE = { noBaseline: 'No baseline', yourSettings: 'Your settings', tuned: 'Optimized' }

export const DOMAIN_LABELS: Record<AutovalidateDomain, DomainLabels> = {
  kb: {
    baselineTile: COMMON_TILE,
    scoreFloorLabel: 'Score to beat (no baseline)',
    scoreFloorDescription:
      'How well the model answers without your knowledge base. The tuned KB needs to clear this bar to be worth keeping.',
    liftLabel: 'better than no baseline',
  },
  extraction: {
    baselineTile: COMMON_TILE,
    scoreFloorLabel: 'Score to beat (no baseline)',
    scoreFloorDescription:
      'How well extraction performs with no custom settings. The tuned result needs to clear this bar to be worth keeping.',
    liftLabel: 'better than no baseline',
  },
  workflow: {
    baselineTile: COMMON_TILE,
    scoreFloorLabel: 'Score to beat (no baseline)',
    scoreFloorDescription:
      'How well a single-shot LLM call performs without the workflow. The tuned workflow needs to clear this bar to be worth keeping.',
    liftLabel: 'better than no baseline',
  },
}
