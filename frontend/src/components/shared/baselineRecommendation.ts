/**
 * Shared helpers for the Baseline wizard step in KB + Extraction Autovalidate.
 *
 * A no-baseline probe returns a 0-1 score: "without your settings, the model
 * gets X% right." That score drives two decisions:
 *
 *   1. Which budget tier to recommend — high baseline score → smaller budget
 *      (less room to improve); low baseline score → tuning has real work to do.
 *   2. What to *tell* the user about why we recommended that tier.
 *
 * The thresholds and copy are intentionally identical across domains so the
 * UX feels coherent when a user moves from KB → Extraction tuning. Domains
 * map the abstract level ('small' / 'medium') to their own tier IDs.
 */

/** Abstract recommendation level — domains map this to their own tier id. */
export type BaselineRecLevel = 'small' | 'medium'

/**
 * Map a no-baseline score (0-1) to a recommendation level. Returns 'medium'
 * as the safe default when the score is null (no judgeable test cases).
 */
export function recommendLevel(noBaselineScore: number | null): BaselineRecLevel {
  if (noBaselineScore == null) return 'medium'
  if (noBaselineScore >= 0.85) return 'small'
  return 'medium'
}

/**
 * Human-readable explanation of why a particular tier was recommended.
 * Returns undefined when there's no score to explain.
 *
 * `withoutLabel` is parameterized so the same sentence frame works for KB
 * ("without the KB") and Extraction ("without custom settings").
 */
export function recommendationReason(
  noBaselineScore: number | null,
  ctx: { withoutLabel: string },
): string | undefined {
  if (noBaselineScore == null) return undefined
  const pct = Math.round(noBaselineScore * 100)
  const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
  if (noBaselineScore >= 0.85) {
    return `The baseline score on these test cases is ${pct}% ${ctx.withoutLabel}. Start with a smaller budget to test whether tuning helps. This sample may not represent other questions.`
  }
  if (noBaselineScore < 0.6) {
    return `${cap(ctx.withoutLabel)}, the baseline score on these test cases is ${pct}%. Standard is a starting budget for comparing settings. A larger budget does not guarantee better answers.`
  }
  return `${cap(ctx.withoutLabel)}, the baseline score on these test cases is ${pct}%. Standard is a starting budget; results depend on the questions and may not generalize.`
}
