import { describe, it, expect } from 'vitest'
import { describeKBScoreWithValues, explainKBScore } from './kbScoreFormula'

describe('explainKBScore', () => {
  it('prefers what the run persisted', () => {
    const out = explainKBScore({
      score_formula: 'overall = persisted',
      score_components: [{ key: 'judge', label: 'answer accuracy (judge)', weight: 0.4, value: 12 }],
    })
    expect(out.formula).toBe('overall = persisted')
    expect(out.components[0].value).toBe(12)
  })

  it('derives the judged formula for an older run — the ticket shape', () => {
    // 83.6% answer accuracy, everything else perfect → overall ≈ 93
    const out = explainKBScore({
      num_test_queries: 95,
      source_health: { ratio: 1 },
      chunk_coverage: { ratio: 1 },
      retrieval_precision: { avg_precision: 1, avg_judge_score: 0.836, num_queries_judged: 95 },
    })
    expect(out.formula).toBe(
      'overall = 40% × answer accuracy (judge) + 25% × retrieval precision + 20% × source health + 15% × chunk coverage',
    )
    expect(out.components.map(c => [c.key, c.weight, c.value])).toEqual([
      ['judge', 0.4, 83.6],
      ['retrieval_precision', 0.25, 100],
      ['source_health', 0.2, 100],
      ['chunk_coverage', 0.15, 100],
    ])
    expect(describeKBScoreWithValues(out.components)).toBe(
      '40% × answer accuracy (judge) 84% + 25% × retrieval precision 100% + 20% × source health 100% + 15% × chunk coverage 100%',
    )
  })

  it('drops the judge term when nothing was judged', () => {
    const out = explainKBScore({
      num_test_queries: 4,
      source_health: { ratio: 1 },
      chunk_coverage: { ratio: 0.5 },
      retrieval_precision: { avg_precision: 0.8, avg_judge_score: null, num_queries_judged: 0 },
    })
    expect(out.components.map(c => c.key)).toEqual(['retrieval_precision', 'source_health', 'chunk_coverage'])
    expect(out.formula).not.toContain('answer accuracy')
  })

  it('scores health and coverage alone with no test queries', () => {
    const out = explainKBScore({ num_test_queries: 0, source_health: { ratio: 0.5 }, chunk_coverage: { ratio: 1 } })
    expect(out.formula).toBe('overall = 60% × source health + 40% × chunk coverage')
  })
})
