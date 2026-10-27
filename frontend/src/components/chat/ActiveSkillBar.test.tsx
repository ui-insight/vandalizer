import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ActiveSkillBar } from './ActiveSkillBar'

it('shows the pinned instructions as text and lets the user change or remove the Skill', () => {
  const onChoose = vi.fn()
  const onRemove = vi.fn()
  render(<ActiveSkillBar skill={{ uuid: 's', version: 'v', title: 'Review', instructions: '<script>bad()</script>' }} busy={false} onChoose={onChoose} onRemove={onRemove} />)
  expect(screen.getByText('Skill: Review')).toBeInTheDocument()
  fireEvent.click(screen.getByText('Inspect instructions'))
  expect(screen.getByText('<script>bad()</script>').tagName).toBe('PRE')
  fireEvent.click(screen.getByRole('button', { name: 'Change Skill' }))
  fireEvent.click(screen.getByRole('button', { name: 'Remove Skill' }))
  expect(onChoose).toHaveBeenCalledOnce()
  expect(onRemove).toHaveBeenCalledOnce()
})

it('disables selection during a turn or pending request', () => {
  render(<ActiveSkillBar skill={null} busy onChoose={vi.fn()} onRemove={vi.fn()} />)
  expect(screen.getByRole('button', { name: 'Choose Skill' })).toBeDisabled()
})
