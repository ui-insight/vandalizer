import { fireEvent, render, screen, within } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { SelfAssessment } from './SelfAssessment'

it('ignores a second activation before the parent can render its saving state', async () => {
  let finish!: () => void
  const submit = vi.fn(() => new Promise<void>(resolve => { finish = resolve }))
  render(<SelfAssessment moduleId="ai_literacy" submitting={false} onSubmit={submit} />)
  for (const group of screen.getAllByRole('radiogroup')) fireEvent.click(within(group).getAllByRole('radio')[1])
  const button = screen.getByRole('button', { name: 'Submit Self-Assessment' })
  fireEvent.click(button)
  fireEvent.click(button)
  expect(submit).toHaveBeenCalledOnce()
  finish()
  await Promise.resolve()
  fireEvent.click(button)
  expect(submit).toHaveBeenCalledTimes(2)
  finish()
})

it('groups required reflection choices by question and preserves the submitted choices while saving', () => {
  const submit = vi.fn()
  const { rerender } = render(<SelfAssessment moduleId="ai_literacy" submitting={false} onSubmit={submit} />)
  const groups = screen.getAllByRole('radiogroup')
  expect(groups).toHaveLength(3)
  expect(screen.getByRole('radiogroup', { name: 'Which best describes your experience with AI tools?' })).toBeInTheDocument()
  for (const group of groups) {
    expect(group).toHaveAttribute('aria-required', 'true')
    expect(group).toHaveAccessibleDescription('Select one answer for each question. All questions are required.')
    fireEvent.click(within(group).getAllByRole('radio')[1])
  }
  fireEvent.click(screen.getByRole('button', { name: 'Submit Self-Assessment' }))
  expect(submit).toHaveBeenCalledOnce()
  const selected = screen.getAllByRole('radio', { checked: true }).map(radio => (radio as HTMLInputElement).value)
  expect(Object.values(submit.mock.calls[0][0])).toEqual(selected)
  rerender(<SelfAssessment moduleId="ai_literacy" submitting onSubmit={submit} />)
  for (const radio of screen.getAllByRole('radio')) expect(radio).toBeDisabled()
  expect(screen.getAllByRole('radio', { checked: true }).map(radio => (radio as HTMLInputElement).value)).toEqual(selected)
})
