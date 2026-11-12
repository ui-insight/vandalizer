import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { QualityBadge } from './QualityBadge'

describe('QualityBadge', () => {
  it('leads with descriptive quality and exposes the exact score in evaluation details', () => {
    const openItem = vi.fn()
    render(<div onClick={openItem}><QualityBadge tier="excellent" score={95} testCaseCount={40} lastValidatedAt="2026-10-28T12:00:00Z" /></div>)
    const summary = screen.getByLabelText('Strong on tested examples. View evaluation')
    expect(summary).toHaveTextContent('Tested on 40 examples')
    expect(summary).not.toHaveTextContent('95')
    expect(screen.getByText(/Recorded score: 95\/100/)).not.toBeVisible()
    fireEvent.click(summary)
    expect(screen.getByRole('region', { name: 'Evaluation details' })).toHaveTextContent('95/100')
    expect(openItem).not.toHaveBeenCalled()
  })
  it('shows low measured scores as needing improvement, not missing validation', () => {
    render(<QualityBadge tier={null} score={0} />)
    expect(screen.getByText('Needs improvement')).toBeVisible()
  })
  it('shows limited evidence alongside strong performance', () => {
    render(<QualityBadge tier="good" score={80} testCaseCount={2} />)
    expect(screen.getByText('Strong on tested examples')).toBeVisible()
    expect(screen.getByText('Limited evidence')).toBeVisible()
  })
  it('does not endorse an author assertion or a tier without a measured score', () => {
    render(<QualityBadge tier="excellent" score={null} asserted />)
    expect(screen.getByText('Not evaluated')).toBeVisible()
    expect(screen.getByText('Author rating · no measured evaluation')).toBeVisible()
    expect(screen.queryByText('Strong on tested examples')).not.toBeInTheDocument()
  })
  it('prioritizes regressions over outdated and high-scoring evaluations', () => {
    render(<QualityBadge tier="excellent" score={99} outdated regressionPending />)
    expect(screen.getByText('Needs review')).toBeVisible()
    fireEvent.click(screen.getByLabelText('Needs review. View evaluation'))
    expect(screen.getByRole('region')).toHaveTextContent('A regression is awaiting review')
  })
  it('shows an outdated evaluation without claiming that its performance is current', () => {
    render(<QualityBadge tier="excellent" score={99} outdated />)
    expect(screen.getByText('Evaluation outdated')).toBeVisible()
    expect(screen.queryByText('Strong on tested examples')).not.toBeInTheDocument()
  })
})
