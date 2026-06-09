import { describe, it, expect } from 'vitest'
import type { OptimizationTrial, TrialConfig } from '../../api/knowledge'
import {
  describeTrialPlainly,
  explainEarlyStop,
  explainTrialOutcome,
  explainTrialParameters,
  formatModel,
} from './trialExplanations'

function cfg(overrides: Partial<TrialConfig> = {}): TrialConfig {
  return {
    k: 8,
    model: 'claude-opus',
    prompt_variant: 'default',
    query_rewriting: false,
    source_label_visibility: true,
    rerank: 'off',
    answer_temperature: 0.0,
    ...overrides,
  }
}

function trial(overrides: Partial<OptimizationTrial> = {}): OptimizationTrial {
  return {
    trial_id: 't1',
    config: cfg(),
    score: 0.78,
    lift_vs_default: 0.06,
    tokens_used: 1234,
    status: 'completed',
    ...overrides,
  }
}

describe('formatModel', () => {
  it('passes through a real model id', () => {
    expect(formatModel('claude-opus')).toBe('claude-opus')
  })
  it('labels null/empty as the default model', () => {
    expect(formatModel(null)).toBe('Default model')
    expect(formatModel('')).toBe('Default model')
    expect(formatModel(undefined)).toBe('Default model')
  })
})

describe('explainTrialParameters', () => {
  it('returns an entry for every knob', () => {
    const params = explainTrialParameters(cfg())
    const keys = params.map((p) => p.key)
    expect(keys).toEqual([
      'k', 'model', 'prompt_variant', 'query_rewriting',
      'rerank', 'source_label_visibility', 'answer_temperature',
    ])
    // Every entry has a non-empty human label, value, and rationale.
    for (const p of params) {
      expect(p.label.length).toBeGreaterThan(0)
      expect(p.value.length).toBeGreaterThan(0)
      expect(p.why.length).toBeGreaterThan(0)
    }
  })

  it('shows the k value and reflects it in the rationale', () => {
    const k = explainTrialParameters(cfg({ k: 12 })).find((p) => p.key === 'k')!
    expect(k.value).toBe('12')
    expect(k.why).toContain('12')
  })

  it('describes each prompt variant distinctly', () => {
    const strict = explainTrialParameters(cfg({ prompt_variant: 'strict' })).find((p) => p.key === 'prompt_variant')!
    const concise = explainTrialParameters(cfg({ prompt_variant: 'concise' })).find((p) => p.key === 'prompt_variant')!
    expect(strict.value).toBe('Strict')
    expect(concise.value).toBe('Concise')
    expect(strict.why).not.toBe(concise.why)
  })

  it('explains on vs off for boolean knobs', () => {
    const on = explainTrialParameters(cfg({ query_rewriting: true })).find((p) => p.key === 'query_rewriting')!
    const off = explainTrialParameters(cfg({ query_rewriting: false })).find((p) => p.key === 'query_rewriting')!
    expect(on.value).toBe('On')
    expect(off.value).toBe('Off')
    expect(on.why).not.toBe(off.why)
  })

  it('defaults missing optional axes the way the backend does', () => {
    // Older runs omit rerank / answer_temperature entirely.
    const legacy = cfg()
    delete (legacy as Partial<TrialConfig>).rerank
    delete (legacy as Partial<TrialConfig>).answer_temperature
    const params = explainTrialParameters(legacy)
    expect(params.find((p) => p.key === 'rerank')!.value).toBe('Off')
    expect(params.find((p) => p.key === 'answer_temperature')!.value).toContain('0')
  })
})

describe('describeTrialPlainly', () => {
  it('builds a capitalized sentence mentioning the passage count', () => {
    const s = describeTrialPlainly(cfg({ k: 8 }))
    expect(s).toMatch(/^[A-Z]/)
    expect(s.endsWith('.')).toBe(true)
    expect(s).toContain('8 passages')
  })

  it('mentions rewriting and reranking only when enabled', () => {
    const plain = describeTrialPlainly(cfg())
    expect(plain).not.toContain('rephras')
    expect(plain).not.toContain('re-ranked')
    const fancy = describeTrialPlainly(cfg({ query_rewriting: true, rerank: 'llm' }))
    expect(fancy).toContain('rephras')
    expect(fancy).toContain('re-ranked')
  })

  it('notes hidden source titles and non-zero temperature', () => {
    const s = describeTrialPlainly(cfg({ source_label_visibility: false, answer_temperature: 0.3 }))
    expect(s).toContain('without seeing source titles')
    expect(s).toContain('temperature 0.3')
  })
})

describe('explainEarlyStop', () => {
  it('explains each early-stop reason and nothing otherwise', () => {
    expect(explainEarlyStop('below_no_kb')).toContain('no knowledge base')
    expect(explainEarlyStop('below_best')).toContain('best configuration')
    expect(explainEarlyStop(undefined)).toBeNull()
  })
})

describe('explainTrialOutcome', () => {
  it('frames a positive lift as higher than current', () => {
    const s = explainTrialOutcome(trial({ score: 0.78, lift_vs_default: 0.06 }))
    expect(s).toContain('78%')
    expect(s).toContain('6 points higher')
  })
  it('frames a negative lift as lower than current', () => {
    const s = explainTrialOutcome(trial({ score: 0.6, lift_vs_default: -0.04 }))
    expect(s).toContain('4 points lower')
  })
  it('handles a tie and a missing lift', () => {
    expect(explainTrialOutcome(trial({ lift_vs_default: 0 }))).toContain('tied')
    expect(explainTrialOutcome(trial({ lift_vs_default: null }))).toContain('scored')
  })
  it('reports a failed trial plainly', () => {
    expect(explainTrialOutcome(trial({ status: 'failed' }))).toContain('failed')
  })
})
