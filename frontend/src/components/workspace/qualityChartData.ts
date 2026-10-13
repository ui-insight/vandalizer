import type { QualityHistoryRun } from '../../api/extractions'

export interface QualityChartPoint {
  label: string
  /** The run's score, the same number the run table shows. */
  score: number
  /** The score before the sample-size penalty; null when there was none. */
  raw: number | null
}

/**
 * Points for the Quality History chart, oldest first. The chart plots the
 * score the table shows; it used to plot the score before the sample-size
 * penalty, so a 62 in the table drew near 100 with nothing saying why. The
 * pre-penalty score is kept as a separate, labeled series.
 */
export function qualityChartData(runs: QualityHistoryRun[]): QualityChartPoint[] {
  return [...runs].reverse().map(r => {
    const penalty = r.score_breakdown?.sample_size_penalty ?? 0
    const d = new Date(r.created_at)
    return {
      // Two runs on the same day otherwise share one label.
      label: `${d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} ${d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}`,
      score: Math.round(r.score),
      raw: penalty > 0 && r.score_breakdown ? Math.round(r.score_breakdown.raw_score) : null,
    }
  })
}
