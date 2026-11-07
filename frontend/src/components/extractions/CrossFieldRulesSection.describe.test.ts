import { describe, expect, it, vi } from 'vitest'

vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))

import { describeRule } from './CrossFieldRulesSection'

// The Budget Analyzer's arithmetic rules (#1013) use two rule types the
// extraction's rules editor must be able to show and describe.
describe('describeRule', () => {
  it('describes a rate applied to a base', () => {
    expect(describeRule({
      type: 'product_equals', base_field: 'Indirect Cost Base', rate_field: 'Indirect Cost Rate', target_field: 'Indirect Costs',
    })).toBe('Indirect Costs = Indirect Cost Base × Indirect Cost Rate')
  })

  it('describes an upper bound by a difference', () => {
    expect(describeRule({
      type: 'at_most_difference', field: 'Indirect Cost Base', minuend_field: 'Total Direct Costs',
      subtrahend_fields: ['Equipment', 'Participant Support Costs'],
    })).toBe('Indirect Cost Base ≤ Total Direct Costs − Equipment − Participant Support Costs')
  })
})
