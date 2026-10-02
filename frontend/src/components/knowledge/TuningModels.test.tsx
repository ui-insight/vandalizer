import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { KBOptimizationModelPlan, KBOptimizationRun } from '../../api/knowledge'

const getModels = vi.fn()
vi.mock('../../api/knowledge', () => ({
  getKBOptimizationModels: (...a: unknown[]) => getModels(...a),
}))
// The results view pulls history over the network; not under test here.
vi.mock('./OptimizationHistoryPanel', () => ({ OptimizationHistoryPanel: () => null }))

import { TuningModelsPicker } from './TuningModels'
import { OptimizationResults } from './OptimizationResults'

const PLAN: KBOptimizationModelPlan = {
  judge_model: 'claude-3-opus',
  judge_source: 'validation_grader',
  judge_model_fallback: null,
  validation_grader: 'claude-3-opus',
  current_model: 'gpt-oss-120b',
  challenger_models: ['gpt-oss-120b', 'glm-4.5'],
  current_shares_judge_family: false,
  models: [
    { name: 'gpt-oss-120b', family: 'gpt', is_current: true, eligible: true, ineligible_reason: null },
    { name: 'glm-4.5', family: 'glm', is_current: false, eligible: true, ineligible_reason: null },
    {
      name: 'claude-3-haiku', family: 'claude', is_current: false, eligible: false,
      ineligible_reason: 'Same family as the judge (claude). A judge over-rates answers from its own family.',
    },
    { name: 'claude-3-opus', family: 'claude', is_current: false, eligible: false, ineligible_reason: 'It is the judge.' },
  ],
}

// Support ticket: tuning silently judged with the chat model, so switching
// the chat model flipped the winner, and nobody could see who judged.
describe('TuningModelsPicker', () => {
  beforeEach(() => { getModels.mockReset(); getModels.mockResolvedValue(PLAN) })

  it('always shows judge, current model, challengers, trials and questions', async () => {
    render(
      <TuningModelsPicker
        kbUuid="kb-1" judgeModel={null} challengerModels={null} onChange={vi.fn()}
        questionCount={12} trialsLabel="up to 25"
      />,
    )
    const summary = await screen.findByTestId('tuning-plan-summary')
    expect(summary).toHaveTextContent('claude-3-opus · Validation grader')
    expect(summary).toHaveTextContent('Current answer model' + 'gpt-oss-120b')
    expect(summary).toHaveTextContent('gpt-oss-120b, glm-4.5')
    expect(summary).toHaveTextContent('up to 25')
    expect(summary).toHaveTextContent('12')
    // The pickers stay behind the Advanced toggle.
    expect(screen.queryByRole('combobox')).toBeNull()
  })

  it('greys out the judge and its family with the reason', async () => {
    render(
      <TuningModelsPicker
        kbUuid="kb-1" judgeModel={null} challengerModels={null} onChange={vi.fn()}
        questionCount={1} trialsLabel="up to 5"
      />,
    )
    fireEvent.click(await screen.findByText(/Advanced: choose the judge/))
    const haiku = screen.getByRole('checkbox', { name: /claude-3-haiku/ })
    expect(haiku).toBeDisabled()
    expect(screen.getByText(/Same family as the judge \(claude\)/)).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /claude-3-opus/ })).toBeDisabled()
    expect(screen.getByText('It is the judge.')).toBeInTheDocument()
  })

  it('narrows challengers and picks a judge', async () => {
    const onChange = vi.fn()
    render(
      <TuningModelsPicker
        kbUuid="kb-1" judgeModel={null} challengerModels={null} onChange={onChange}
        questionCount={1} trialsLabel="up to 5"
      />,
    )
    fireEvent.click(await screen.findByText(/Advanced: choose the judge/))
    fireEvent.click(screen.getByRole('checkbox', { name: /glm-4.5/ }))
    expect(onChange).toHaveBeenLastCalledWith(null, ['gpt-oss-120b'])
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'glm-4.5' } })
    expect(onChange).toHaveBeenLastCalledWith('glm-4.5', null)
  })
})

function makeRun(overrides: Partial<KBOptimizationRun>): KBOptimizationRun {
  return {
    uuid: 'opt-1', kb_uuid: 'kb-1', status: 'completed', phase: 'done',
    progress_message: '', current_trial_index: 2, total_trials_planned: 2,
    best_score_so_far: 0.8, best_config_so_far: null, token_budget: 500_000,
    tokens_used: 1000, estimated_cost_usd: null, actual_cost_usd: null,
    baseline_no_kb_score: 0.3, baseline_default_score: 0.7, optimized_score: 0.8,
    judge_variance: 0.02, judge_model: 'claude-3-opus',
    judge_source: 'validation_grader', current_model: 'gpt-oss-120b',
    challenger_models: ['gpt-oss-120b', 'glm-4.5'],
    default_config: { k: 8, model: null, prompt_variant: 'default', query_rewriting: false, source_label_visibility: true },
    best_config: { k: 8, model: 'glm-4.5', prompt_variant: 'default', query_rewriting: false, source_label_visibility: true },
    trials: [], data_source_suggestions: [], options: {}, error_message: null,
    started_at: null, completed_at: null, cancel_requested: false,
    ...overrides,
  } as KBOptimizationRun
}

function renderResults(run: KBOptimizationRun) {
  render(
    <OptimizationResults
      run={run} canManage onApply={vi.fn()} applying={false} onRunAgain={vi.fn()}
    />,
  )
}

describe('OptimizationResults winner', () => {
  it('names the challenger and what Apply would change', () => {
    renderResults(makeRun({ winner: 'challenger' }))
    expect(screen.getByText('Winner: glm-4.5 + tuned settings')).toBeInTheDocument()
    expect(screen.getByText('Apply would change 1 setting:')).toBeInTheDocument()
    // The current side of the diff names the model, not "default".
    expect(screen.getByText('gpt-oss-120b')).toBeInTheDocument()
    expect(screen.getByTestId('tuning-models-line')).toHaveTextContent(
      'Judged by claude-3-opus (Validation grader) · current model gpt-oss-120b · challengers gpt-oss-120b, glm-4.5',
    )
  })

  it('says the current settings won and offers nothing to apply', () => {
    renderResults(makeRun({ winner: 'current', tied_with_baseline: false }))
    expect(screen.getByText('Winner: current settings')).toBeInTheDocument()
    expect(screen.getByText(/Every setup we tried scored below your current settings/)).toBeInTheDocument()
    expect(screen.queryByText(/Winner: glm-4.5/)).toBeNull()
    expect(screen.queryByRole('button', { name: /Apply/ })).toBeNull()
  })

  it('treats an older tied run as a current-settings win', () => {
    renderResults(makeRun({ winner: undefined, tied_with_baseline: true }))
    expect(screen.getByText('Winner: current settings')).toBeInTheDocument()
  })
})
