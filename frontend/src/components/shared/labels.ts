/**
 * Per-domain copy for the three Autovalidate surfaces (KB / Extraction /
 * Workflow). Centralized so the next time the wording shifts it doesn't drift
 * three ways.
 *
 * The tile trio is deliberately per-domain and self-describing. The earlier
 * generic trio (No baseline / Your settings / Tuned) tested badly: users who
 * never touched a setting couldn't map "Your settings" to anything, and
 * "No baseline" didn't say what was removed. Each label must answer "what
 * configuration produced this bar?" on its own, without the tooltip.
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

export const DOMAIN_LABELS: Record<AutovalidateDomain, DomainLabels> = {
  kb: {
    baselineTile: {
      noBaseline: 'Model alone (no KB)',
      yourSettings: 'Current KB settings',
      tuned: 'Optimized KB settings',
    },
    scoreFloorLabel: 'Score to beat (model alone)',
    scoreFloorDescription:
      'How well the model answers without your knowledge base. The tuned KB needs to clear this bar to be worth keeping.',
    liftLabel: 'better than the model alone',
  },
  extraction: {
    baselineTile: {
      noBaseline: 'No custom settings',
      yourSettings: 'Current settings',
      tuned: 'Optimized settings',
    },
    scoreFloorLabel: 'Score to beat (no custom settings)',
    scoreFloorDescription:
      'How well extraction performs with no custom settings. The tuned result needs to clear this bar to be worth keeping.',
    liftLabel: 'better than no custom settings',
  },
  workflow: {
    baselineTile: {
      noBaseline: 'LLM alone (no workflow)',
      yourSettings: 'Current workflow',
      tuned: 'Optimized workflow',
    },
    scoreFloorLabel: 'Score to beat (LLM alone)',
    scoreFloorDescription:
      'How well a single-shot LLM call performs without the workflow. The tuned workflow needs to clear this bar to be worth keeping.',
    liftLabel: 'better than the LLM alone',
  },
}
