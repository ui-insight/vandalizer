import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/certification'
import { ChatPracticeCheck } from './ChatPracticeCheck'
vi.mock('../../api/certification', () => ({ checkChatPractice: vi.fn() }))
const practice = { document: 'nsf-proposal-alpine-ecology.pdf', bounded_question: 'What total amount does this proposal request?', unanswerable_question: 'What indirect cost rate does this proposal use?' }
beforeEach(() => vi.resetAllMocks())
it('sends the learner record and shows practice-only feedback', async () => {
  vi.mocked(api.checkChatPractice).mockResolvedValue({ passage_found: true, quote_supports_value: true, value_matches: true, judgment_correct: false,
    practice_complete: false, feedback: ['The document lists amounts but states no rate.'], saved: false, credit_awarded: false })
  render(<ChatPracticeCheck enrollmentId="enrollment" practice={practice} />)
  expect(screen.getByText(/What indirect cost rate does this proposal use\?/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText(/Supporting passage you opened/), { target: { value: 'Requested Amount: $485,000' } })
  fireEvent.change(screen.getByLabelText('The value the passage states'), { target: { value: '485000' } })
  const check = screen.getByRole('button', { name: 'Check my practice' })
  expect(check).toBeDisabled()
  fireEvent.click(screen.getByRole('radio', { name: 'Yes, a passage supports it' }))
  fireEvent.click(check)
  expect(await screen.findByText('Not yet.')).toBeInTheDocument()
  expect(screen.getByText('The document lists amounts but states no rate.')).toBeInTheDocument()
  expect(screen.getByText(/nothing was saved and no credit changed/)).toBeInTheDocument()
  expect(api.checkChatPractice).toHaveBeenCalledWith('enrollment', { passage_quote: 'Requested Amount: $485,000', page: 1, value: '485000', unanswerable_judgment: 'supported_by_source' })
})
