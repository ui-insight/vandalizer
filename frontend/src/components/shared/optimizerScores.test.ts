import { describe, expect, it } from 'vitest'
import { isHeldOutHeadline, reportedBaselineScore } from './optimizerScores'

describe('reportedBaselineScore', () => {
  it('pairs a held-out headline with the held-out current score', () => {
    const run = { optimized_score: 0.95, baseline_default_score: 0.93, holdout_default_score: 0.94, holdout_optimized_score: 0.95 }
    expect(isHeldOutHeadline(run)).toBe(true)
    expect(reportedBaselineScore(run)).toBe(0.94)
  })

  it('recognises older held-out runs by a headline that differs from the training score', () => {
    const run = { optimized_score: 0.95, optimized_score_train: 0.88, baseline_default_score: 0.93, holdout_default_score: 0.94 }
    expect(reportedBaselineScore(run)).toBe(0.94)
  })

  it('keeps the training baseline when the headline is the training score', () => {
    expect(reportedBaselineScore({ optimized_score: 0.9, optimized_score_train: 0.9, baseline_default_score: 0.85, holdout_default_score: 0.8 })).toBe(0.85)
    expect(reportedBaselineScore({ optimized_score: 0.9, baseline_default_score: 0.85 })).toBe(0.85)
  })
})
