import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QualityBadge } from './QualityBadge'

describe('QualityBadge', () => {
  it('renders "excellent" tier with score', () => {
    render(<QualityBadge tier="excellent" score={95} />)
    expect(screen.getByText('Quality: Excellent (95%)')).toBeTruthy()
  })

  it('renders "good" tier with score', () => {
    render(<QualityBadge tier="good" score={78} />)
    expect(screen.getByText('Quality: Good (78%)')).toBeTruthy()
  })

  it('renders "fair" tier with score', () => {
    render(<QualityBadge tier="fair" score={55} />)
    expect(screen.getByText('Quality: Fair (55%)')).toBeTruthy()
  })

  it('renders "Unvalidated" when tier is null', () => {
    render(<QualityBadge tier={null} score={null} />)
    expect(screen.getByText('Unvalidated')).toBeTruthy()
  })

  it('renders tier name without percentage when score is null', () => {
    render(<QualityBadge tier="good" score={null} />)
    expect(screen.getByText('Quality: Good')).toBeTruthy()
  })

  it('rounds score to nearest integer', () => {
    render(<QualityBadge tier="excellent" score={92.7} />)
    expect(screen.getByText('Quality: Excellent (93%)')).toBeTruthy()
  })

  it('replaces the tier with the pending-review state after a regression', () => {
    render(<QualityBadge tier="excellent" score={95} regressionPending />)
    expect(screen.getByText('Regression pending review')).toBeTruthy()
    expect(screen.queryByText('Quality: Excellent (95%)')).toBeNull()
  })

  it('renders an asserted tier in the neutral style, in plain words', () => {
    // A seeded "excellent" with no measured score is a claim, not a rating.
    render(<QualityBadge tier="excellent" score={null} asserted />)
    const badge = screen.getByText('Rated Excellent by its author · not yet checked here')
    expect(badge.getAttribute('title')).toContain('Nobody here has run a validation')
    expect(badge.style.color).not.toBe('rgb(21, 128, 61)')
  })

  it('leads with "Checked" on a shared entry and says when nothing was', () => {
    render(<QualityBadge tier="good" score={87} variant="catalog" />)
    expect(screen.getByText('Checked · Good (87%)')).toBeTruthy()
  })

  it('says "Not yet checked here" for a shared entry with no tier at all', () => {
    render(<QualityBadge tier={null} score={null} variant="catalog" />)
    expect(screen.getByText('Not yet checked here')).toBeTruthy()
  })

  it('ignores the asserted flag when there is no tier to assert', () => {
    render(<QualityBadge tier={null} score={null} asserted />)
    expect(screen.getByText('Unvalidated')).toBeTruthy()
  })

  it('explains the pending-review state on hover', () => {
    render(<QualityBadge tier="good" score={70} regressionPending title="ignored" />)
    const badge = screen.getByText('Regression pending review')
    expect(badge.getAttribute('title')).toContain('no longer applies')
  })
})
