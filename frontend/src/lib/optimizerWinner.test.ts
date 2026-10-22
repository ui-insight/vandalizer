import { describe, expect, it } from 'vitest'
import type { ExtractionTrial } from '../api/extractions'
import { winnerTrials } from './optimizerWinner'

const trial = (trial_id: string, score: number | null, config: Record<string, unknown>, status = 'completed') =>
  ({ trial_id, score, config, status, accuracy: null, consistency: null, lift_vs_default: null, tokens_used: 0 }) as ExtractionTrial

const simple = trial('t-simple', 0.85, { strategy: 'one-pass' })
const top = trial('t-top', 0.94, { strategy: 'two-pass', consensus: true })
const failed = trial('t-failed', null, {}, 'failed')

describe('winnerTrials', () => {
  it('tells the reported setup apart from the top scorer on a tie', () => {
    const { bestTrial, topTrial } = winnerTrials({ trials: [simple, top, failed], best_trial_id: 't-simple', best_config: simple.config })
    expect(bestTrial).toBe(simple)
    expect(topTrial).toBe(top)
  })

  it('matches an older run by its configuration', () => {
    expect(winnerTrials({ trials: [simple, top], best_config: { strategy: 'two-pass', consensus: true } }).bestTrial).toBe(top)
  })
})
