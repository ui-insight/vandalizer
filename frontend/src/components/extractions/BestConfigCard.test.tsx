import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ExtractionTrial } from '../../api/extractions'
import { BestConfigCard } from './ExtractionAutovalidatePanel'

const trial = (trial_id: string, score: number, config: Record<string, unknown>) =>
  ({ trial_id, score, config, status: 'completed', accuracy: null, consistency: null, lift_vs_default: null, tokens_used: 0 }) as ExtractionTrial
const simple = trial('t-simple', 0.85, { strategy: 'one-pass', model: 'gpt-oss-120b' })
const top = trial('t-top', 0.94, { strategy: 'two-pass', model: 'gpt-oss-120b', consensus: { enabled: true } })
const props = { canManage: false, isPast: false, isAlreadyApplied: false, onApply: vi.fn(), applying: false, onRevert: vi.fn(), reverting: false }

// Support ticket: on a tie the card read "Best configuration" over an 85% setup
// while the top trial scored 94%, with nothing saying why.
describe('best configuration card', () => {
  it('says a tied result is the simplest equivalent setup and shows both scores', () => {
    render(<BestConfigCard {...props} config={simple.config} tied bestTrial={simple} topTrial={top} />)
    expect(screen.getByText('No meaningful difference: simplest equivalent setup')).toBeInTheDocument()
    expect(screen.queryByText('Best configuration')).not.toBeInTheDocument()
    expect(screen.getByText('This setup scored 85% in the trials.')).toBeInTheDocument()
    expect(screen.getByText(/Top-scoring trial for comparison: 94%/)).toBeInTheDocument()
  })

  it('keeps the plain title and its score when the winner beat the current settings', () => {
    render(<BestConfigCard {...props} config={top.config} tied={false} bestTrial={top} topTrial={top} />)
    expect(screen.getByText('Best configuration')).toBeInTheDocument()
    expect(screen.getByText('This setup scored 94% in the trials.')).toBeInTheDocument()
    expect(screen.queryByText(/Top-scoring trial/)).not.toBeInTheDocument()
  })
})
