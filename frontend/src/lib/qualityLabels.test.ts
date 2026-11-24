import { describe, expect, it } from 'vitest'
import { qualityPresentation } from './qualityLabels'

describe('quality presentation', () => {
  it('uses configured tiers rather than applying a new percentage cutoff', () => {
    expect(qualityPresentation({ score: 95, tier: 'excellent' }).label).toBe('Strong on tested examples')
    expect(qualityPresentation({ score: 78, tier: 'good' }).label).toBe('Strong on tested examples')
    expect(qualityPresentation({ score: 95, tier: 'fair' }).label).toBe('Mixed results')
  })
  it('distinguishes a measured zero, absent evaluation and missing tier metadata', () => {
    expect(qualityPresentation({ score: 0, tier: null }).label).toBe('Needs improvement')
    expect(qualityPresentation({ score: null, tier: 'excellent' }).label).toBe('Not evaluated')
    expect(qualityPresentation({ score: 95 }).label).toBe('Evaluation recorded')
    expect(qualityPresentation({ score: NaN, tier: 'excellent' }).measured).toBe(false)
  })
  it('keeps sample size separate from performance and author assertions', () => {
    const small = qualityPresentation({ score: 100, tier: 'excellent', testCaseCount: 2 })
    expect(small.label).toBe('Strong on tested examples')
    expect(small.evidence).toBe('Limited evidence')
    expect(qualityPresentation({ score: 95, tier: 'excellent', asserted: true }).measured).toBe(false)
    expect(qualityPresentation({ score: 95, tier: 'excellent' }).evidence).toBe('Sample size not recorded')
  })
  it('puts known problems and outdated evaluations before a reassuring rating', () => {
    expect(qualityPresentation({ score: 100, tier: 'excellent', outdated: true }).label).toBe('Evaluation outdated')
    expect(qualityPresentation({ score: 100, tier: 'excellent', outdated: true, needsReview: true }).label).toBe('Needs review')
    expect(qualityPresentation({ score: null, needsReview: true }).label).toBe('Needs review')
  })
  it('interprets workflow rubric grades without inventing a percentage', () => {
    expect(qualityPresentation({ grade: 'B' }).label).toBe('Strong on tested examples')
    expect(qualityPresentation({ grade: 'C' }).label).toBe('Mixed results')
    expect(qualityPresentation({ grade: 'F' }).label).toBe('Needs improvement')
  })
})
