import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ValidationResults } from './ValidationResults'
import { observeCertificationJourney } from '../../api/certificationJourney'
vi.mock('../../api/certificationJourney', () => ({ observeCertificationJourney: vi.fn() }))

it('names the course, uses its star scale and offers a recorded way to question a versioned result', () => {
  const identity = { enrollment_id: 'a'.repeat(32), manifest_sha256: 'b'.repeat(64), course_title: 'Research Workflow Practitioner', course_version: 'course-5.0.0', maximum_stars: 1 }
  render(<ValidationResults result={{ ...identity, passed: true, stars: 1, checks: [{ name: 'Run completed', passed: true, detail: '' }] }} onDismiss={vi.fn()} />)
  expect(screen.getByText('Checked against Research Workflow Practitioner (version course-5.0.0)')).toBeInTheDocument()
  expect(screen.getByRole('img', { name: '1 of 1 stars' })).toBeInTheDocument()
  expect(screen.queryByText(/b{64}/)).not.toBeInTheDocument()
  const link = screen.getByRole('link', { name: 'Question this result' })
  expect(link).toHaveAttribute('href', '/support')
  fireEvent.click(link)
  expect(observeCertificationJourney).toHaveBeenCalledExactlyOnceWith('grading_question_opened', { enrollment_id: identity.enrollment_id, manifest_sha256: identity.manifest_sha256 })
})

it('does not offer a grading question path for the legacy course, which has no correction record', () => {
  render(<ValidationResults result={{ passed: false, stars: 0, checks: [{ name: 'Run completed', passed: false, detail: '' }] }} onDismiss={vi.fn()} />)
  expect(screen.queryByRole('link', { name: 'Question this result' })).not.toBeInTheDocument()
  expect(screen.queryByText(/Checked against/)).not.toBeInTheDocument()
})

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
