import { describe, it, expect } from 'vitest'
import { qualityChartData } from './qualityChartData'
import type { QualityHistoryRun } from '../../api/extractions'

const run = (score: number, raw: number | null, created_at: string): QualityHistoryRun => ({
  uuid: created_at, score, accuracy: null, consistency: null, grade: null, model: null, created_at, num_test_cases: 1,
  score_breakdown: raw == null ? null : {
    raw_score: raw, final_score: score, sample_size_factor: score / raw, sample_size_penalty: raw - score,
    num_test_cases: 1, num_runs: 1, test_cases_needed: 2, runs_needed: 2,
  },
})

describe('qualityChartData (ticket: chart drew 62 and 85 near 100)', () => {
  it('plots the score the run table shows, oldest first', () => {
    // History arrives newest first.
    const data = qualityChartData([run(85, 99, '2026-10-13T15:00:00Z'), run(62, 98, '2026-10-13T14:00:00Z')])
    expect(data.map(d => d.score)).toEqual([62, 85])
  })

  it('keeps the score before the penalty as its own series', () => {
    const data = qualityChartData([run(85, 99, '2026-10-13T15:00:00Z'), run(90, null, '2026-10-12T15:00:00Z')])
    expect(data.map(d => d.raw)).toEqual([null, 99])
  })

  it('gives two runs on the same day different labels', () => {
    const data = qualityChartData([run(85, null, '2026-10-13T15:00:00Z'), run(62, null, '2026-10-13T14:00:00Z')])
    expect(data[0].label).not.toEqual(data[1].label)
  })
})
