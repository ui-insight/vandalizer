/** The score fields every optimizer run (KB, extraction, workflow) carries. */
export interface OptimizerHeadlineScores {
  optimized_score: number | null
  baseline_default_score: number | null
  optimized_score_train?: number | null
  holdout_default_score?: number | null
  holdout_optimized_score?: number | null
}

/**
 * Whether the run's headline score was measured on held-out cases. Runs from
 * before ``holdout_optimized_score`` existed are recognised by a headline that
 * differs from the training score. Mirrors the backend's
 * ``optimization_summary._held_out_headline``.
 */
export function isHeldOutHeadline(run: OptimizerHeadlineScores): boolean {
  if (run.holdout_optimized_score != null) return true
  return run.holdout_default_score != null
    && run.optimized_score != null
    && run.optimized_score_train != null
    && run.optimized_score !== run.optimized_score_train
}

/**
 * The current settings' score, measured on the same cases as the headline.
 * Paired with the training-case score instead, the editor showed Optimized
 * 95% against Current 93% while chat and the Apply gate each read a
 * different gap. Mirrors the backend's ``reported_baseline_score``.
 */
export function reportedBaselineScore(run: OptimizerHeadlineScores): number | null {
  if (isHeldOutHeadline(run) && run.holdout_default_score != null) return run.holdout_default_score
  return run.baseline_default_score
}
