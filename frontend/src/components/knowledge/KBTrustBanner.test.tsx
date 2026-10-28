import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AITrustChip } from './AITrustChip'
import { KBTrustBanner } from './KBTrustBanner'

describe('KBTrustBanner', () => {
  it.each(['proposed', 'applied', 'reverted', 'default'] as const)('labels composite quality and %s provenance without inventing accuracy lift', configState => {
    render(<KBTrustBanner score={0.8} baseline={0.4} lift={0.4} metric="composite_quality" configState={configState} />)
    expect(screen.getByText(/Evaluation recorded/)).toBeVisible()
    expect(screen.getByText(/Composite quality: 80/)).not.toBeVisible()
    fireEvent.click(screen.getByText('View evaluation'))
    expect(screen.getByText(/Composite quality: 80/)).toBeVisible()
    expect(screen.queryByText('+40 pts')).not.toBeInTheDocument()
    expect(screen.queryByText(/Average answer accuracy/)).not.toBeInTheDocument()
  })
  it('says a run that found no improvement kept the settings, and asks for nothing', () => {
    const { rerender } = render(<KBTrustBanner score={0.8} metric="composite_quality" configState="no_improvement" />)
    expect(screen.getByText(/Evaluation recorded · No improvement found/)).toBeVisible()
    expect(screen.getByText(/current settings were kept and there is nothing to apply/)).toBeVisible()
    expect(screen.queryByText(/Proposed settings/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Review and apply/)).not.toBeInTheDocument()
    rerender(<AITrustChip score={0.8} metric="composite_quality" configState="no_improvement" />)
    expect(screen.getByText('Evaluation recorded · no improvement found')).toBeVisible()
  })
  it('keeps measured answer-only and composite chips distinct from an untested KB', () => {
    const { rerender } = render(<AITrustChip score={0.7} />)
    expect(screen.getByText('Evaluation recorded')).toBeVisible()
    expect(screen.queryByText('Answer accuracy 70%')).not.toBeInTheDocument()
    rerender(<AITrustChip score={0.8} metric="composite_quality" configState="proposed" />)
    expect(screen.getByText('Evaluation recorded · proposed')).toBeVisible()
    expect(screen.queryByText('Not evaluated')).not.toBeInTheDocument()
  })
  it('recognizes answer-only grading without claiming a comparison', () => {
    render(<KBTrustBanner score={0.72} />)
    expect(screen.getByText(/Average answer accuracy: 72%/)).not.toBeVisible()
    fireEvent.click(screen.getByText('View evaluation'))
    expect(screen.getByText(/Average answer accuracy: 72%/)).toBeVisible()
    expect(screen.getByText(/no AI-only comparison yet/)).toBeVisible()
    expect(screen.queryByText('Not evaluated')).not.toBeInTheDocument()
  })
  it('derives a negative comparison from the two scores when lift is absent', () => {
    render(<KBTrustBanner score={0.5} baseline={0.7} />)
    fireEvent.click(screen.getByText('View evaluation'))
    expect(screen.getByText('Difference: -20 pts on tested questions')).toBeVisible()
    expect(screen.getByText('No measured improvement over the AI alone')).toBeVisible()
  })
  it('keeps a measured zero distinct from an unmeasured score', () => {
    render(<KBTrustBanner score={0} baseline={0} lift={0} />)
    fireEvent.click(screen.getByText('View evaluation'))
    expect(screen.getByText('Difference: 0 pts on tested questions')).toBeVisible()
    expect(screen.queryByText('Not evaluated')).not.toBeInTheDocument()
  })
})
