import { describe, it, expect } from 'vitest'
import type { WorkflowOptimizationTrial } from '../../api/workflows'
import {
  describeWorkflowTrialPlainly,
  explainWorkflowOutcome,
  explainWorkflowSteps,
  promptVariantLabel,
  summariseWorkflowTrialConfig,
} from './workflowTrialExplanations'

function trial(
  stepOverrides: Record<string, { model?: string; prompt_variant?: string | null }>,
  overrides: Partial<WorkflowOptimizationTrial> = {},
): WorkflowOptimizationTrial {
  return {
    trial_id: 't1',
    config: { step_overrides: stepOverrides },
    score: 0.75,
    weighted_pass_rate: 0.8,
    lift_vs_default: 0.04,
    tokens_used: 2000,
    status: 'completed',
    duration_seconds: 12.3,
    step_breakdown: [],
    error: null,
    num_inputs_run: 5,
    num_inputs_total: 5,
    ...overrides,
  }
}

describe('promptVariantLabel', () => {
  it('maps known variants and defaults gracefully', () => {
    expect(promptVariantLabel('cot')).toBe('Step-by-step')
    expect(promptVariantLabel('strict')).toBe('Strict')
    expect(promptVariantLabel(null)).toBe('Default')
    expect(promptVariantLabel('mystery')).toBe('mystery')
  })
})

describe('explainWorkflowSteps', () => {
  it('produces one entry per overridden step with model + prompt', () => {
    const steps = explainWorkflowSteps({
      step_overrides: {
        Extract: { model: 'claude-opus', prompt_variant: 'strict' },
        Summarize: { model: undefined, prompt_variant: 'default' },
      },
    })
    expect(steps).toHaveLength(2)
    const extract = steps.find((s) => s.step === 'Extract')!
    expect(extract.model).toBe('claude-opus')
    expect(extract.promptVariant).toBe('Strict')
    expect(extract.promptWhy.length).toBeGreaterThan(0)

    const summarize = steps.find((s) => s.step === 'Summarize')!
    expect(summarize.model).toBe('Default model')
    expect(summarize.promptVariant).toBe('Default')
    // No "why" for the default variant — nothing changed.
    expect(summarize.promptWhy).toBe('')
  })

  it('handles an empty override map', () => {
    expect(explainWorkflowSteps({ step_overrides: {} })).toEqual([])
    expect(explainWorkflowSteps({})).toEqual([])
  })
})

describe('summariseWorkflowTrialConfig', () => {
  it('summarizes step count + distinct models/variants', () => {
    const c = {
      step_overrides: {
        A: { model: 'opus', prompt_variant: 'cot' },
        B: { model: 'opus', prompt_variant: 'default' },
      },
    }
    const terse = summariseWorkflowTrialConfig(c)
    expect(terse).toContain('2 steps')
    expect(terse).toContain('opus')
    expect(terse.toLowerCase()).toContain('step-by-step')
    expect(summariseWorkflowTrialConfig(c, true)).toContain('2 steps tuned')
  })

  it('falls back when there are no overrides', () => {
    expect(summariseWorkflowTrialConfig({ step_overrides: {} })).toBe('current settings')
  })
})

describe('describeWorkflowTrialPlainly', () => {
  it('names the first steps and notes there are more', () => {
    const s = describeWorkflowTrialPlainly({
      step_overrides: {
        A: { model: 'opus', prompt_variant: 'strict' },
        B: { model: 'haiku', prompt_variant: 'default' },
        C: { model: 'opus', prompt_variant: 'cot' },
      },
    })
    expect(s).toContain('3 of the workflow')
    expect(s).toContain('“A”')
    expect(s).toContain('and others')
  })

  it('describes the no-override case', () => {
    expect(describeWorkflowTrialPlainly({ step_overrides: {} })).toContain('current settings')
  })
})

describe('explainWorkflowOutcome', () => {
  it('frames lift directions, ties and failures', () => {
    expect(explainWorkflowOutcome(trial({}, { score: 0.75, lift_vs_default: 0.04 }))).toContain('4 points higher')
    expect(explainWorkflowOutcome(trial({}, { score: 0.5, lift_vs_default: -0.06 }))).toContain('6 points lower')
    expect(explainWorkflowOutcome(trial({}, { lift_vs_default: 0 }))).toContain('tied')
    expect(explainWorkflowOutcome(trial({}, { status: 'failed' }))).toContain('failed')
  })
})
