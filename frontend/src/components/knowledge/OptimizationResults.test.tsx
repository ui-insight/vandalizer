import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { KBOptimizationRun } from '../../api/knowledge'
import { OptimizationResults } from './OptimizationResults'
vi.mock('./OptimizationHistoryPanel', () => ({ OptimizationHistoryPanel: () => null }))
vi.mock('./TrialExplainerModal', () => ({ TrialExplainerModal: () => null }))
const run = { status: 'completed', trials: [], data_source_suggestions: [], baseline_no_kb_score: 0.4, baseline_default_score: 0.65, optimized_score: 0.8, judge_variance: 0.01, best_config: { k: 8 }, default_config: { k: 4 }, options: { apply_on_finish: true }, applied_at: null, reverted_at: null } as unknown as KBOptimizationRun
const props = { run, canManage: true, applying: false, onApply: vi.fn(), onRunAgain: vi.fn() }
describe('optimization result semantics', () => {
  it('compares composite scores only and requires evidence of application', () => {
    render(<OptimizationResults {...props} />)
    expect(screen.getByText(/AI-only answer accuracy: 40%/)).toBeVisible()
    expect(screen.queryByText(/\+40pts over/)).not.toBeInTheDocument()
    expect(screen.queryByText('Model alone (no KB)')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Apply optimized settings' })).toBeEnabled()
    expect(screen.queryByText('These settings are applied')).not.toBeInTheDocument()
  })
  it('compares the two raw judge scores in a cross-judge check', () => {
    render(<OptimizationResults {...props} run={{ ...run, cross_judge: { model: 'second', score: 0.7, delta: -0.2, tokens_used: 100 } }} />)
    expect(screen.getByText(/scored 90%/)).toBeVisible()
  })
})
