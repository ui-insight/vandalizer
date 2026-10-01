import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { QualityBadge } from './QualityBadge'
import type { QualityMeta } from '../../types/chat'

it('opens readable evidence details and returns focus on Escape without implying live settings', () => {
  const quality = { tier: 'good', score: 80, num_test_cases: 2, last_validated_at: null, optimization: { pending_recommendation: true, optimized_score: 85, baseline_score: 70 } } as QualityMeta
  render(<QualityBadge quality={quality} />)
  const button = screen.getByRole('button', { name: /Quality Good, score 80/ })
  fireEvent.click(button)
  const details = screen.getByRole('region', { name: 'Tool quality details' })
  expect(details).toHaveFocus()
  expect(details).toHaveTextContent('85 vs 70 baseline')
  expect(details).toHaveTextContent('do not establish correctness on new documents')
  fireEvent.keyDown(details, { key: 'Escape' })
  expect(screen.queryByRole('region', { name: 'Tool quality details' })).not.toBeInTheDocument()
  expect(button).toHaveFocus()
})
