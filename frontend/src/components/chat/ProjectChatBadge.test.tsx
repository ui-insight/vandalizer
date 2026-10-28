import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { ProjectChatBadge } from './ProjectChatBadge'
const state = vi.hoisted(() => ({ context: '' }))
vi.mock('../../hooks/useProjects', () => ({ useProject: () => ({ project: { title: 'Grant', context: state.context, capabilities: { knowledge: { ready: true } } } }) }))
beforeEach(() => { state.context = '' })
it('shows no empty context control and lets users inspect an active brief', () => {
  const view = render(<ProjectChatBadge projectUuid="p1" fallbackTitle="Grant" onExit={vi.fn()} />)
  expect(screen.queryByRole('button', { name: 'View project context' })).not.toBeInTheDocument()
  state.context = 'Goals and audience for this project'
  view.rerender(<ProjectChatBadge projectUuid="p1" fallbackTitle="Grant" onExit={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'View project context' }))
  expect(screen.getByRole('dialog', { name: 'Project context' })).toHaveTextContent(state.context)
  fireEvent.click(screen.getByRole('button', { name: 'Close Project context' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})
