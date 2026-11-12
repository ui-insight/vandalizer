import type { ExtractionOptimizationRun, ExtractionTrial } from '../api/extractions'

/**
 * The trial an optimizer run's reported configuration came from, and the
 * top-scoring trial. When the top trial is within noise of the current
 * settings, the run reports the simplest tied setup instead of the top
 * scorer, so the two can differ. Older runs don't record best_trial_id;
 * their configuration is matched against the trials instead.
 */
export function winnerTrials(run: Pick<ExtractionOptimizationRun, 'trials' | 'best_trial_id' | 'best_config'>) {
  const scored = (run.trials || []).filter(t => t.status === 'completed' && t.score != null)
  const topTrial = scored.reduce<ExtractionTrial | null>(
    (top, t) => (top == null || (t.score as number) > (top.score as number) ? t : top), null,
  )
  const sameConfig = (t: ExtractionTrial) => JSON.stringify(t.config) === JSON.stringify(run.best_config)
  const bestTrial = scored.find(t => run.best_trial_id != null && t.trial_id === run.best_trial_id)
    ?? (run.best_config ? scored.find(sameConfig) : undefined) ?? null
  return { bestTrial, topTrial }
}
