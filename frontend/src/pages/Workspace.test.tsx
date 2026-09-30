import { useState, type ReactNode } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { Workspace } from './Workspace'
const h = vi.hoisted(() => ({ user: { id: 'user-a', current_team: 'team-a' } }))
vi.mock('../hooks/useAuth', () => ({ useAuth: () => ({ user: h.user }) }))
vi.mock('../contexts/WorkspaceContext', () => ({ WorkspaceProvider: ({ children }: { children: ReactNode }) => {
  const [draft, setDraft] = useState('')
  return <><input aria-label="Provider state" value={draft} onChange={e => setDraft(e.target.value)} />{children}</>
} }))
vi.mock('../contexts/WorkspaceTourContext', () => ({ WorkspaceTourProvider: ({ children }: { children: ReactNode }) => children }))
vi.mock('../components/workspace/WorkspaceLayout', () => ({ WorkspaceLayout: () => {
  const [draft, setDraft] = useState('')
  return <input aria-label="Panel draft" value={draft} onChange={e => setDraft(e.target.value)} />
} }))
beforeEach(() => { h.user = { id: 'user-a', current_team: 'team-a' } })
it('resets retained views on team changes while allowing the provider to clear scope', () => {
  const { rerender } = render(<Workspace />)
  fireEvent.change(screen.getByRole('textbox', { name: 'Provider state' }), { target: { value: 'Provider remains mounted' } })
  fireEvent.change(screen.getByRole('textbox', { name: 'Panel draft' }), { target: { value: 'Old team draft' } })
  h.user = { ...h.user, current_team: 'team-b' }; rerender(<Workspace />)
  expect(screen.getByRole('textbox', { name: 'Panel draft' })).toHaveValue('')
  expect(screen.getByRole('textbox', { name: 'Provider state' })).toHaveValue('Provider remains mounted')
  h.user = { ...h.user, id: 'user-b' }; rerender(<Workspace />)
  expect(screen.getByRole('textbox', { name: 'Provider state' })).toHaveValue('')
})
