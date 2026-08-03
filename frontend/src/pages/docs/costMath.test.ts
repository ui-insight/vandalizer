import { describe, expect, it } from 'vitest'
import {
  MODEL_PRICES,
  OPERATIONS,
  WORKLOAD_PRESETS,
  estimate,
  formatTokens,
  formatUsd,
  type Operation,
} from './costMath'

const OP: Operation[] = [
  {
    id: 'a',
    label: 'A',
    unit: 'runs',
    description: '',
    inputTokens: 1_000_000,
    outputTokens: 100_000,
  },
]

describe('estimate', () => {
  it('bills input and output at their respective per-MTok rates', () => {
    const r = estimate({
      counts: { a: 1 },
      inputPerMTok: 5,
      outputPerMTok: 25,
      users: 1,
      operations: OP,
    })
    // 1M input @ $5 + 0.1M output @ $25 = $5.00 + $2.50
    expect(r.costPerUser).toBeCloseTo(7.5, 10)
  })

  it('scales the deployment total by user count', () => {
    const r = estimate({
      counts: { a: 1 },
      inputPerMTok: 5,
      outputPerMTok: 25,
      users: 20,
      operations: OP,
    })
    expect(r.costTotal).toBeCloseTo(r.costPerUser * 20, 10)
  })

  it('discounts the cached share of input tokens to 10% of the input rate', () => {
    const r = estimate({
      counts: { a: 1 },
      inputPerMTok: 10,
      outputPerMTok: 0,
      users: 1,
      cacheHitRate: 0.5,
      operations: OP,
    })
    // Half at $10, half at $1 → blended $5.50 per MTok.
    expect(r.costPerUser).toBeCloseTo(5.5, 10)
  })

  it('clamps a cache hit rate above 1 rather than inverting the cost', () => {
    const r = estimate({
      counts: { a: 1 },
      inputPerMTok: 10,
      outputPerMTok: 0,
      users: 1,
      cacheHitRate: 5,
      operations: OP,
    })
    expect(r.costPerUser).toBeCloseTo(1, 10)
  })

  it('treats blank, negative, and NaN fields as zero instead of producing NaN', () => {
    const r = estimate({
      counts: { a: Number.NaN },
      inputPerMTok: Number.NaN,
      outputPerMTok: -5,
      users: -3,
      operations: OP,
    })
    expect(r.costPerUser).toBe(0)
    expect(r.costTotal).toBe(0)
    expect(Number.isNaN(r.inputTokens)).toBe(false)
  })

  it('sums token totals across every operation', () => {
    const r = estimate({
      counts: { classification: 10, extraction: 2 },
      inputPerMTok: 1,
      outputPerMTok: 1,
      users: 1,
    })
    // 10 uploads (3k in) + 2 extractions (30k in), others zeroed.
    expect(r.inputTokens).toBe(10 * 3_000 + 2 * 30_000)
    expect(r.outputTokens).toBe(10 * 300 + 2 * 2_000)
  })

  it('ranks the shipped presets by cost, light through heavy', () => {
    const costs = WORKLOAD_PRESETS.map(
      (p) =>
        estimate({ counts: p.counts, inputPerMTok: 5, outputPerMTok: 25, users: 1 }).costPerUser,
    )
    expect(costs[0]).toBeLessThan(costs[1])
    expect(costs[1]).toBeLessThan(costs[2])
  })
})

describe('catalog integrity', () => {
  it('gives every preset a volume for every operation', () => {
    for (const preset of WORKLOAD_PRESETS) {
      for (const op of OPERATIONS) {
        expect(preset.counts[op.id]).toBeDefined()
      }
    }
  })

  it('prices every model with positive rates and unique ids', () => {
    const ids = MODEL_PRICES.map((m) => m.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const m of MODEL_PRICES) {
      expect(m.inputPerMTok).toBeGreaterThan(0)
      expect(m.outputPerMTok).toBeGreaterThan(0)
    }
  })
})

describe('formatting', () => {
  it('formats currency, collapsing sub-cent values', () => {
    expect(formatUsd(12.345)).toBe('$12.35')
    expect(formatUsd(0.004)).toBe('<$0.01')
    expect(formatUsd(0)).toBe('$0.00')
    expect(formatUsd(Number.NaN)).toBe('$0.00')
  })

  it('abbreviates token counts by magnitude', () => {
    expect(formatTokens(950)).toBe('950')
    expect(formatTokens(12_000)).toBe('12K')
    expect(formatTokens(3_400_000)).toBe('3.4M')
    expect(formatTokens(2_000_000_000)).toBe('2.0B')
    expect(formatTokens(0)).toBe('0')
  })
})
