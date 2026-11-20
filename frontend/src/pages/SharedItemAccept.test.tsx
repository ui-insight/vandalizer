import { StrictMode } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ redeem: vi.fn(), navigate: vi.fn() }))
let search: Record<string, string | undefined> = {}
let auth: { user: unknown; loading: boolean } = { user: { email: 'ra@example.test' }, loading: false }
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => api.navigate, useSearch: () => search }))
vi.mock('../hooks/useAuth', () => ({ useAuth: () => auth }))
vi.mock('../api/extractions', () => ({ redeemSearchSetShareToken: api.redeem }))

import SharedItemAccept from './SharedItemAccept'

beforeEach(() => {
  vi.clearAllMocks()
  search = { item: 'skill-1', token: 'tok' }
  auth = { user: { email: 'ra@example.test' }, loading: false }
})

it('opens a shared Skill in a new chat, once', async () => {
  api.redeem.mockResolvedValue({ uuid: 'skill-1', title: 'Award review', set_type: 'prompt' })
  render(<StrictMode><SharedItemAccept /></StrictMode>)

  await waitFor(() => expect(api.navigate).toHaveBeenCalled())
  expect(api.redeem).toHaveBeenCalledTimes(1)
  expect(api.redeem).toHaveBeenCalledWith('skill-1', 'tok')
  const target = api.navigate.mock.calls[0][0]
  expect(target.to).toBe('/')
  expect(target.replace).toBe(true)
  expect(target.search).toMatchObject({ mode: 'chat', skill: 'skill-1', extraction: undefined })
  // The token must not travel on into the workspace address.
  expect(JSON.stringify(target.search)).not.toContain('tok')
})

it('opens a shared extraction in the Library', async () => {
  api.redeem.mockResolvedValue({ uuid: 'ss-9', title: 'NOA fields', set_type: 'extraction' })
  render(<SharedItemAccept />)

  await waitFor(() => expect(api.navigate).toHaveBeenCalled())
  const target = api.navigate.mock.calls[0][0]
  expect(target.search).toMatchObject({ tab: 'library', extraction: 'ss-9' })
  expect(target.search.skill).toBeUndefined()
})

it('says so when the link is not valid, and opens nothing', async () => {
  api.redeem.mockRejectedValue(new Error('This share link is not valid. Ask for a new one.'))
  render(<SharedItemAccept />)

  expect(await screen.findByRole('alert')).toHaveTextContent('This share link is not valid. Ask for a new one.')
  expect(api.navigate).not.toHaveBeenCalled()
})

it('asks a signed-out person to sign in before anything is recorded', async () => {
  auth = { user: null, loading: false }
  render(<SharedItemAccept />)

  expect(await screen.findByText('Sign in or create an account, then re-open this link.')).toBeInTheDocument()
  expect(api.redeem).not.toHaveBeenCalled()
})

it('waits for sign-in state, and rejects a link with a part missing', async () => {
  auth = { user: null, loading: true }
  const { unmount } = render(<SharedItemAccept />)
  expect(screen.getByRole('status')).toHaveTextContent('Opening the shared item…')
  expect(api.redeem).not.toHaveBeenCalled()
  unmount()

  auth = { user: { email: 'ra@example.test' }, loading: false }
  search = { item: 'skill-1' }
  render(<SharedItemAccept />)
  expect(await screen.findByRole('alert')).toHaveTextContent('This share link is incomplete.')
  expect(api.redeem).not.toHaveBeenCalled()
})
