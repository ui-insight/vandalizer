import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ProtectedRoute, resetPendingNextForTests } from './ProtectedRoute'
import { rememberPendingNext } from '../../lib/pendingNext'

// University single sign-on returns to "/", so a link opened while signed out
// (a knowledge base's chat link from SharePoint) was dropped on the way back.

const auth = vi.hoisted(() => ({ user: { id: 'u1' } as { id: string } | null }))
vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ user: auth.user, loading: false, demoExpired: false, demoFeedbackToken: null }),
}))
vi.mock('@tanstack/react-router', () => ({
  Navigate: ({ to, search }: { to: string; search?: { next?: string } }) => (
    <div data-testid="navigate" data-to={to} data-next={search?.next ?? ''} />
  ),
}))

const replace = vi.fn()
const realLocation = window.location

beforeEach(() => {
  sessionStorage.clear()
  resetPendingNextForTests()
  replace.mockClear()
  auth.user = { id: 'u1' }
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { pathname: '/', search: '', replace },
  })
})
afterEach(() => {
  Object.defineProperty(window, 'location', { configurable: true, value: realLocation })
})

it('goes to the link that was opened before single sign-on', async () => {
  rememberPendingNext('/?kb=kb-1')
  render(<ProtectedRoute><p>workspace</p></ProtectedRoute>)
  await waitFor(() => expect(replace).toHaveBeenCalledWith('/?kb=kb-1'))
  expect(screen.queryByText('workspace')).toBeNull()
})

it('shows the page when nothing was parked', () => {
  render(<ProtectedRoute><p>workspace</p></ProtectedRoute>)
  expect(screen.getByText('workspace')).toBeInTheDocument()
  expect(replace).not.toHaveBeenCalled()
})

it('does not reload when already on the parked link', () => {
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { pathname: '/', search: '?kb=kb-1', replace },
  })
  rememberPendingNext('/?kb=kb-1')
  render(<ProtectedRoute><p>workspace</p></ProtectedRoute>)
  expect(screen.getByText('workspace')).toBeInTheDocument()
  expect(replace).not.toHaveBeenCalled()
})

it('leaves the parked link alone while signed out, and sends the visitor to sign in with it', () => {
  auth.user = null
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { pathname: '/', search: '?kb=kb-1', replace },
  })
  render(<ProtectedRoute><p>workspace</p></ProtectedRoute>)
  expect(screen.getByTestId('navigate').dataset.to).toBe('/landing')
  expect(screen.getByTestId('navigate').dataset.next).toBe('/?kb=kb-1')
})
