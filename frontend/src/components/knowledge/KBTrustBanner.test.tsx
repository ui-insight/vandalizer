import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AITrustChip } from './AITrustChip'
import { KBTrustBanner } from './KBTrustBanner'

describe('KBTrustBanner', () => {
  it.each(['proposed', 'applied', 'reverted', 'default'] as const)('labels composite quality and %s provenance without inventing accuracy lift', configState => {
    render(<KBTrustBanner score={0.8} baseline={0.4} lift={0.4} metric="composite_quality" configState={configState} />)
    expect(screen.getByText(/Composite quality: 80/)).toBeVisible()
    expect(screen.queryByText('+40 pts')).not.toBeInTheDocument()
    expect(screen.queryByText(/Average answer accuracy/)).not.toBeInTheDocument()
  })
  it('keeps measured answer-only and composite chips distinct from an untested KB', () => {
    const { rerender } = render(<AITrustChip score={0.7} />)
    expect(screen.getByText('Answer accuracy 70%')).toBeVisible()
    rerender(<AITrustChip score={0.8} metric="composite_quality" configState="proposed" />)
    expect(screen.getByText('Quality 80/100 · proposed')).toBeVisible()
    expect(screen.queryByText('Not yet validated')).not.toBeInTheDocument()
  })
  it('recognizes answer-only grading without claiming a comparison', () => {
    render(<KBTrustBanner score={0.72} />)
    expect(screen.getByText(/Average answer accuracy: 72%/)).toBeVisible()
    expect(screen.getByText(/no AI-only comparison yet/)).toBeVisible()
    expect(screen.queryByText('Answer quality not yet measured')).not.toBeInTheDocument()
  })
  it('derives a negative comparison from the two scores when lift is absent', () => {
    render(<KBTrustBanner score={0.5} baseline={0.7} />)
    expect(screen.getByText('-20 pts')).toBeVisible()
    expect(screen.getByText('no measured improvement over the AI alone')).toBeVisible()
  })
  it('keeps a measured zero distinct from an unmeasured score', () => {
    render(<KBTrustBanner score={0} baseline={0} lift={0} />)
    expect(screen.getByText('0 pts')).toBeVisible()
    expect(screen.queryByText('Answer quality not yet measured')).not.toBeInTheDocument()
  })
})
