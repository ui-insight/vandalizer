import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { ProjectChatBadge } from './ProjectChatBadge'
const state = vi.hoisted(() => ({ context: '', loaded: true, files: 0, indexed: 0, ready: true }))
vi.mock('../../hooks/useProjects', () => ({ useProject: () => ({ project: state.loaded ? { title: 'Grant', context: state.context, capabilities: { files: { count: state.files }, knowledge: { ready: state.ready, documents: state.indexed } } } : undefined }) }))
beforeEach(() => { Object.assign(state, { context: '', loaded: true, files: 0, indexed: 0, ready: true }) })
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


it.each([
  [0, 0, true, 'No documents yet'],
  [0, 0, false, 'No documents yet'],
  [2, 0, true, 'No documents indexed yet'],
  [2, 0, false, 'Knowledge not ready'],
  [2, 1, true, 'Knowledge available · 1 indexed document'],
  [2, 2, true, 'Knowledge available · 2 indexed documents'],
] as const)('reports source availability for %s files and %s indexed documents (ready: %s)', (files, indexed, ready, text) => {
  Object.assign(state, { files, indexed, ready })
  render(<ProjectChatBadge projectUuid="p1" fallbackTitle="Grant" onExit={vi.fn()} />)
  expect(screen.getByText(text)).toBeInTheDocument()
  expect(screen.queryByText('Knowledge available · 0 indexed documents')).not.toBeInTheDocument()
})

it('waits for the project before claiming it is empty', () => {
  state.loaded = false
  const view = render(<ProjectChatBadge projectUuid="p1" fallbackTitle="Grant" onExit={vi.fn()} />)
  expect(screen.getByText('Checking availability…')).toBeInTheDocument()
  expect(screen.queryByText('No documents yet')).not.toBeInTheDocument()
  state.loaded = true
  view.rerender(<ProjectChatBadge projectUuid="p1" fallbackTitle="Grant" onExit={vi.fn()} />)
  expect(screen.getByText('No documents yet')).toBeInTheDocument()
})
