import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { QualityBadge } from './QualityBadge'
import type { QualityMeta } from '../../types/chat'

it('opens readable evidence details and returns focus on Escape without implying live settings', () => {
  const quality = { tier: 'good', score: 80, num_test_cases: 2, last_validated_at: null, optimization: { pending_recommendation: true, optimized_score: 0.85, baseline_score: 0.7 } } as QualityMeta
  render(<QualityBadge quality={quality} />)
  const button = screen.getByRole('button', { name: /Quality Good, score 80/ })
  fireEvent.click(button)
  const details = screen.getByRole('region', { name: 'Tool quality details' })
  expect(details).toHaveFocus()
  // get_quality_info sends optimizer scores on a 0..1 scale.
  expect(details).toHaveTextContent('85% vs 70% baseline')
  expect(details).toHaveTextContent('do not establish correctness on new documents')
  fireEvent.keyDown(details, { key: 'Escape' })
  expect(screen.queryByRole('region', { name: 'Tool quality details' })).not.toBeInTheDocument()
  expect(button).toHaveFocus()
})

it('labels an extraction with no validation run Unscored (v5 retest ticket)', () => {
  const quality = { score: null, tier: 'unscored', grade: null, last_validated_at: null, num_test_cases: 0, active_alerts: [] } as QualityMeta
  render(<QualityBadge quality={quality} />)
  const button = screen.getByRole('button', { name: 'Quality Unscored. Show details.' })
  expect(button).toHaveTextContent('Unscored')
  fireEvent.click(button)
  expect(screen.getByRole('region', { name: 'Tool quality details' })).toHaveTextContent('No Score')
})
