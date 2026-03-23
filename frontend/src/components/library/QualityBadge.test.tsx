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
})
