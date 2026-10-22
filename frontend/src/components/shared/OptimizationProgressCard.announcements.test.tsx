import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { OptimizationProgressCard } from './OptimizationProgressCard'

it('announces phase changes without repeating streaming counters and trial text', () => {
  const run = { status: 'running', phase: 'Evaluating', progress_message: 'Trial 1 running', current_trial_index: 1, total_trials_planned: 10, token_budget: 10000, tokens_used: 100, best_score_so_far: null, best_config_so_far: null, trials: [], cancel_requested: false, elapsed_seconds: 1 }
  const props = { scoreFloor: null, summariseConfig: () => '', onCancel: vi.fn(), cancelling: false }
  const { rerender } = render(<OptimizationProgressCard run={run} {...props} />)
  const announcement = screen.getByRole('status').textContent
  rerender(<OptimizationProgressCard run={{ ...run, elapsed_seconds: 2, tokens_used: 200, progress_message: 'Trial 2 running' }} {...props} />)
  expect(screen.getByRole('status').textContent).toBe(announcement)
  expect(screen.getByRole('status')).not.toHaveTextContent('Trial 2')
  rerender(<OptimizationProgressCard run={{ ...run, phase: 'Finalizing' }} {...props} />)
  expect(screen.getByRole('status')).toHaveTextContent('Finalizing')
})
