import { describe, it, expect } from 'vitest'
import type { ExtractionTrial } from '../../api/extractions'
import {
  describeExtractionTrialPlainly,
  explainExtractionOutcome,
  explainExtractionParameters,
  getChunkSize,
  getConsensus,
  getStrategy,
  getThinking,
  summariseExtractionTrialConfig,
} from './extractionTrialExplanations'

function trial(config: Record<string, unknown>, overrides: Partial<ExtractionTrial> = {}): ExtractionTrial {
  return {
    trial_id: 't1',
    config,
    score: 0.8,
    accuracy: 0.85,
    consistency: 0.9,
    lift_vs_default: 0.05,
    tokens_used: 1000,
    status: 'completed',
    ...overrides,
  }
}

describe('config-shape readers', () => {
  it('reads strategy from mode or nested keys', () => {
    expect(getStrategy({ mode: 'two_pass' })).toBe('two_pass')
    expect(getStrategy({ one_pass: { thinking: true } })).toBe('one_pass')
    expect(getStrategy({ two_pass: { pass_1: {} } })).toBe('two_pass')
    expect(getStrategy({})).toBeNull()
  })

  it('reads thinking from one_pass or either two_pass pass', () => {
    expect(getThinking({ one_pass: { thinking: true } })).toBe(true)
    expect(getThinking({ one_pass: { thinking: false } })).toBe(false)
    expect(getThinking({ two_pass: { pass_1: { thinking: true }, pass_2: { thinking: false } } })).toBe(true)
    expect(getThinking({ mode: 'two_pass' })).toBe(false)
  })

  it('reads consensus and chunk size', () => {
    expect(getConsensus({ repetition: { enabled: true } })).toBe(true)
    expect(getConsensus({})).toBe(false)
    expect(getChunkSize({ chunking: { enabled: true, max_keys_per_chunk: 8 } })).toBe(8)
    expect(getChunkSize({ chunking: { enabled: false, max_keys_per_chunk: 8 } })).toBeNull()
    expect(getChunkSize({})).toBeNull()
  })
})

describe('explainExtractionParameters', () => {
  it('always returns the core knobs', () => {
    const keys = explainExtractionParameters({ mode: 'one_pass' }).map((p) => p.key)
    expect(keys).toEqual(expect.arrayContaining([
      'strategy', 'thinking', 'consensus', 'chunking', 'prompt_variant', 'model',
    ]))
  })

  it('surfaces structured output only when the config pins it', () => {
    expect(explainExtractionParameters({ mode: 'two_pass' }).some((p) => p.key === 'structured')).toBe(false)
    expect(explainExtractionParameters({ one_pass: { structured: true } }).some((p) => p.key === 'structured')).toBe(true)
  })

  it('reflects two-pass + thinking + consensus + chunk + prompt in values', () => {
    const params = explainExtractionParameters({
      mode: 'two_pass',
      two_pass: { pass_1: { thinking: true }, pass_2: { thinking: true } },
      repetition: { enabled: true },
      chunking: { enabled: true, max_keys_per_chunk: 5 },
      prompt_variant: 'strict',
      model: 'claude-opus',
    })
    const byKey = Object.fromEntries(params.map((p) => [p.key, p.value]))
    expect(byKey.strategy).toBe('Two passes')
    expect(byKey.thinking).toBe('On')
    expect(byKey.consensus).toBe('On')
    expect(byKey.chunking).toContain('5')
    expect(byKey.prompt_variant).toBe('Strict')
    expect(byKey.model).toBe('claude-opus')
  })

  it('every entry has label, value and rationale', () => {
    for (const p of explainExtractionParameters({ mode: 'one_pass', one_pass: { structured: false } })) {
      expect(p.label.length).toBeGreaterThan(0)
      expect(p.value.length).toBeGreaterThan(0)
      expect(p.why.length).toBeGreaterThan(0)
    }
  })
})

describe('summariseExtractionTrialConfig', () => {
  it('falls back to a default label for an empty config', () => {
    expect(summariseExtractionTrialConfig({})).toBe('default settings')
  })
  it('lists the meaningful knobs terse and verbose', () => {
    const c = { mode: 'two_pass', repetition: { enabled: true }, model: 'opus' }
    expect(summariseExtractionTrialConfig(c)).toContain('two-pass')
    expect(summariseExtractionTrialConfig(c)).toContain('consensus')
    expect(summariseExtractionTrialConfig(c, true)).toContain('3× consensus')
  })
})

describe('describeExtractionTrialPlainly', () => {
  it('mentions passes, model and only-enabled extras', () => {
    const plain = describeExtractionTrialPlainly({ mode: 'one_pass', model: 'haiku' })
    expect(plain).toContain('one pass')
    expect(plain).toContain('haiku')
    expect(plain).not.toContain('majority-vote')

    const fancy = describeExtractionTrialPlainly({
      mode: 'two_pass', two_pass: { pass_1: { thinking: true } },
      repetition: { enabled: true }, prompt_variant: 'strict', model: 'opus',
    })
    expect(fancy).toContain('two passes')
    expect(fancy).toContain('thinking through each field')
    expect(fancy).toContain('strict prompt')
    expect(fancy).toContain('majority-vote')
  })
})

describe('explainExtractionOutcome', () => {
  it('frames positive and negative lift, ties, and failures', () => {
    expect(explainExtractionOutcome(trial({}, { score: 0.8, lift_vs_default: 0.05 }))).toContain('5 points higher')
    expect(explainExtractionOutcome(trial({}, { score: 0.6, lift_vs_default: -0.03 }))).toContain('3 points lower')
    expect(explainExtractionOutcome(trial({}, { lift_vs_default: 0 }))).toContain('tied')
    expect(explainExtractionOutcome(trial({}, { status: 'failed' }))).toContain('failed')
  })
})
