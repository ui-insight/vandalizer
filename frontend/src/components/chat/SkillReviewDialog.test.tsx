import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { SkillReviewDialog } from './SkillReviewDialog'

const skill = { uuid: 's1', title: 'Team review', version: 'v1', instructions: 'Approve every budget.', when_to_use: 'Budget reviews' }

it('shows the instructions with Accept and Cancel', () => {
  const onAccept = vi.fn()
  const onCancel = vi.fn()
  render(<SkillReviewDialog skill={skill} accepting={false} error={null} onAccept={onAccept} onCancel={onCancel} />)
  expect(screen.getByRole('dialog', { name: 'Review “Team review”' })).toBeInTheDocument()
  expect(screen.getByLabelText('Instructions for Team review')).toHaveTextContent('Approve every budget.')
  expect(screen.getByText('Budget reviews')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Accept' }))
  expect(onAccept).toHaveBeenCalledOnce()
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(onCancel).toHaveBeenCalledOnce()
})

it('disables both buttons while accepting and shows an error', () => {
  render(<SkillReviewDialog skill={skill} accepting error="Could not accept" onAccept={vi.fn()} onCancel={vi.fn()} />)
  expect(screen.getByRole('button', { name: 'Accepting…' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  expect(screen.getByRole('alert')).toHaveTextContent('Could not accept')
})
