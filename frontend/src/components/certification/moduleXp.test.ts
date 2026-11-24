import { describe, expect, it } from 'vitest'
import { moduleMaxXp, moduleXpExplanation, moduleXpLabel } from './moduleXp'

// Ticket: AI Literacy showed 50 XP and awarded 125 for 3 stars.
describe('module XP label', () => {
  it('shows the range when stars add XP', () => {
    const max = moduleMaxXp(50, 25, 3)
    expect(max).toBe(125)
    expect(moduleXpLabel(50, max)).toBe('50–125 XP')
    expect(moduleXpExplanation(50, max, 25)).toBe('50 XP for completing this module, plus 25 XP for each star you earn: up to 125 XP')
  })

  it('shows the base alone when stars add nothing', () => {
    expect(moduleXpLabel(100, moduleMaxXp(100, 0, 3))).toBe('100 XP')
    expect(moduleXpLabel(100, undefined)).toBe('100 XP')
    expect(moduleXpExplanation(100, 100)).toBe('100 XP for completing this module')
  })
})
