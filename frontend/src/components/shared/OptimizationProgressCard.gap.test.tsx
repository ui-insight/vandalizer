import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { describeGap, OptimizationProgressCard } from './OptimizationProgressCard'

describe('describeGap', () => {
  it('words the gap by its sign', () => {
    expect(describeGap(3, 'no custom settings')).toBe('3 pts better than no custom settings')
    expect(describeGap(-3, 'no custom settings')).toBe('3 pts worse than no custom settings')
    expect(describeGap(-1, 'the LLM alone')).toBe('1 pt worse than the LLM alone')
    expect(describeGap(0, 'the model alone')).toBe('same as the model alone')
  })
})

// Ticket: "88% · −3pp better than no custom settings" in a green box.
it('a best-so-far that trails the floor says worse and is not shown as a success', () => {
  const run = { status: 'running', phase: 'Evaluating', progress_message: '', current_trial_index: 3, total_trials_planned: 10, token_budget: 10000, tokens_used: 100, best_score_so_far: 0.88, best_config_so_far: null, trials: [], cancel_requested: false, elapsed_seconds: 1 }
  render(<OptimizationProgressCard run={run} scoreFloor={0.91} summariseConfig={() => ''} onCancel={vi.fn()} cancelling={false} baselineName="no custom settings" />)

  const gap = screen.getByText('3 pts worse than no custom settings')
  expect(screen.queryByText(/better than/)).not.toBeInTheDocument()
  expect(gap.parentElement).not.toHaveStyle({ color: 'var(--workspace-success)' })
})
