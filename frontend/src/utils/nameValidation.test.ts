import { describe, expect, it } from 'vitest'
import { getNameError, isDuplicateName, normalizeName } from './nameValidation'

describe('normalizeName', () => {
  it('collapses whitespace runs and trims', () => {
    expect(normalizeName('  Budget \n Analyzer\t ')).toBe('Budget Analyzer')
  })
})

describe('getNameError', () => {
  it('rejects empty names', () => {
    expect(getNameError('   ')).toMatch(/cannot be empty/)
  })

  it('accepts a normal name', () => {
    expect(getNameError('Budget Analyzer')).toBeNull()
  })
})

describe('isDuplicateName', () => {
  const existing = ['Budget Analyzer', 'Award Summary']

  it('matches exact names', () => {
    expect(isDuplicateName('Budget Analyzer', existing)).toBe(true)
  })

  it('matches case-insensitively', () => {
    expect(isDuplicateName('budget ANALYZER', existing)).toBe(true)
  })

  it('matches after whitespace normalization on both sides', () => {
    expect(isDuplicateName('  Budget   Analyzer ', ['Budget Analyzer'])).toBe(true)
  })

  it('does not match different names', () => {
    expect(isDuplicateName('Budget Analyzer v2', existing)).toBe(false)
  })

  it('never flags an empty name', () => {
    expect(isDuplicateName('   ', [''])).toBe(false)
  })
})
