import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ValidationResults } from './ValidationResults'

it('labels optional advice without presenting it as an unmet requirement', () => {
  render(<ValidationResults result={{ passed: true, stars: 1, checks: [
    { name: '15+ extraction fields', role: 'required', passed: true, detail: '' },
    { name: 'Missing expected fields', role: 'advisory', passed: false, detail: 'Consider adding the suggested fields.' },
  ] }} onDismiss={vi.fn()} />)
  expect(screen.getByText('15+ extraction fields')).toHaveTextContent('Required: Met')
  expect(screen.getByText('Missing expected fields')).toHaveTextContent('Advisory: Suggestion')
  expect(screen.getByText('Required checks passed. Advisory suggestions do not block completion.')).toBeVisible()
  expect(screen.queryByText('All checks passed')).not.toBeInTheDocument()
})

it('does not claim all checks passed when the preserved course allows an unmet check', () => {
  render(<ValidationResults result={{ passed: true, stars: 1, checks: [{ name: 'Run completed', passed: true, detail: 'Saved output exists' }, { name: 'Source review', passed: false, detail: 'Review the quoted source before using the output' }] }} onDismiss={vi.fn()} />)
  expect(screen.getByText('Module requirements met')).toBeInTheDocument()
  expect(screen.queryByText('All checks passed')).not.toBeInTheDocument()
  expect(screen.getByText('Source review')).toHaveTextContent('Not met')
  expect(screen.getByRole('img', { name: '1 of 3 stars' })).toBeInTheDocument()
})

it('reserves the all-checks summary for a nonempty set of passing checks', () => {
  const { rerender } = render(<ValidationResults result={{ passed: true, stars: 3, checks: [] }} onDismiss={vi.fn()} />)
  expect(screen.queryByText('All checks passed')).not.toBeInTheDocument()
  rerender(<ValidationResults result={{ passed: true, stars: 3, checks: [{ name: 'Required result', passed: true, detail: '' }] }} onDismiss={vi.fn()} />)
  expect(screen.getByText('All checks passed')).toBeInTheDocument()
})
