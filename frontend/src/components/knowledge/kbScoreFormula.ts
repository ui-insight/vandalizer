// How a KB validation run's overall quality score is assembled.
//
// The overall score is a weighted composite — it is NOT the judge's answer
// accuracy, which is `retrieval_precision.avg_judge_score` on its own. A
// support ticket showed the two being read as the same number, so every
// surface that shows the overall score states the formula next to it.
//
// Runs persist `score_components` / `score_formula` (backend
// `kb_score_components`); older runs are re-derived here from the snapshot's
// ratios with the same weights, mirroring the backend fallback.

export type KBScoreComponent = {
  key: 'judge' | 'retrieval_precision' | 'source_health' | 'chunk_coverage'
  label: string
  weight: number
  value: number
}

export type KBScoreExplanation = {
  formula: string
  components: KBScoreComponent[]
}

type ScoreInputs = {
  num_test_queries?: number | null
  score_formula?: string | null
  score_components?: KBScoreComponent[] | null
  source_health?: { ratio: number } | null
  chunk_coverage?: { ratio: number } | null
  retrieval_precision?: {
    avg_precision?: number | null
    avg_judge_score?: number | null
    num_queries_judged?: number | null
  } | null
}

const LABELS: Record<KBScoreComponent['key'], string> = {
  judge: 'answer accuracy (judge)',
  retrieval_precision: 'retrieval precision',
  source_health: 'source health',
  chunk_coverage: 'chunk coverage',
}

const WEIGHTS_JUDGED: [KBScoreComponent['key'], number][] = [
  ['judge', 0.40], ['retrieval_precision', 0.25], ['source_health', 0.20], ['chunk_coverage', 0.15],
]
const WEIGHTS_RETRIEVAL_ONLY: [KBScoreComponent['key'], number][] = [
  ['retrieval_precision', 0.50], ['source_health', 0.30], ['chunk_coverage', 0.20],
]
const WEIGHTS_NO_QUERIES: [KBScoreComponent['key'], number][] = [
  ['source_health', 0.60], ['chunk_coverage', 0.40],
]

export function formatKBScoreFormula(components: KBScoreComponent[]): string {
  return 'overall = ' + components
    .map(c => `${Math.round(c.weight * 100)}% × ${c.label}`)
    .join(' + ')
}

export function explainKBScore(run: ScoreInputs): KBScoreExplanation {
  if (run.score_components?.length && run.score_formula) {
    return { formula: run.score_formula, components: run.score_components }
  }
  const rp = run.retrieval_precision ?? {}
  const n = run.num_test_queries ?? 0
  const judged = n > 0 && rp.avg_judge_score != null && (rp.num_queries_judged ?? 0) > 0
  const weights = judged ? WEIGHTS_JUDGED : n > 0 ? WEIGHTS_RETRIEVAL_ONLY : WEIGHTS_NO_QUERIES
  const ratios: Record<KBScoreComponent['key'], number | null | undefined> = {
    judge: rp.avg_judge_score,
    retrieval_precision: rp.avg_precision,
    source_health: run.source_health?.ratio,
    chunk_coverage: run.chunk_coverage?.ratio,
  }
  const components = weights.map(([key, weight]) => ({
    key,
    label: LABELS[key],
    weight,
    value: Math.round((ratios[key] ?? 0) * 1000) / 10,
  }))
  return { formula: formatKBScoreFormula(components), components }
}

/** One-line, values-included statement for tooltips:
 *  "40% × answer accuracy (judge) 84% + 25% × retrieval precision 100% + …" */
export function describeKBScoreWithValues(components: KBScoreComponent[]): string {
  return components
    .map(c => `${Math.round(c.weight * 100)}% × ${c.label} ${Math.round(c.value)}%`)
    .join(' + ')
}

/** Hover text for the KB quality badge/chip, where there is no room to print
 *  the formula inline. Says what the number is before saying how good it is. */
export const KB_QUALITY_SCORE_HOVER =
  'Overall quality score — a weighted composite of answer accuracy (judge), retrieval precision, source health, and chunk coverage. Not the answer accuracy on its own; open the KB\'s Validation panel for the breakdown.'
