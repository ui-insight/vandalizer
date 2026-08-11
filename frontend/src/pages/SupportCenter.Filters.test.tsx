import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import SupportCenter from './SupportCenter'

// Regression guard: filters used to live in component state, so a refresh (or
// opening a ticket and coming back) reset the queue to the default Open/no-tag
// view. They now live in the URL — these tests pin both directions of that:
// the URL seeds the query, and changing a filter writes back to the URL.

const mockUseSearch = vi.fn()
const mockNavigate = vi.fn()
const mockListTickets = vi.fn()

vi.mock('@tanstack/react-router', () => ({
  Navigate: () => null,
  useNavigate: () => mockNavigate,
  useSearch: () => mockUseSearch(),
}))

vi.mock('../api/support', () => ({
  listTickets: (...args: unknown[]) => mockListTickets(...args),
  getTicketStats: () => Promise.resolve({ total: 0, open: 0, in_progress: 0, closed: 0 }),
  listAllTags: () => Promise.resolve({ tags: ['billing', 'deploy'] }),
  // Opening a ticket mounts ChatView; leave its fetch pending so it parks on
  // its loading state instead of us having to model a whole ticket payload.
  getTicket: () => new Promise(() => {}),
  markTicketRead: () => Promise.resolve({}),
  createTicket: vi.fn(),
  addMessage: vi.fn(),
  editMessage: vi.fn(),
  deleteMessage: vi.fn(),
  addAttachment: vi.fn(),
  deleteAttachment: vi.fn(),
  updateTicket: vi.fn(),
  addWatcher: vi.fn(),
  removeWatcher: vi.fn(),
}))

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ user: { user_id: 'u1', is_support_agent: true } }),
}))
vi.mock('../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../components/shared/useConfirm', () => ({ useConfirm: () => vi.fn() }))
vi.mock('../components/layout/PageLayout', () => ({
  PageLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('../api/feedback', () => ({
  listPositiveFeedback: vi.fn(),
  getPositiveFeedbackStats: vi.fn(),
}))

beforeEach(() => {
  mockNavigate.mockReset()
  mockListTickets.mockReset()
  mockListTickets.mockResolvedValue({ tickets: [], total: 0, limit: 50, offset: 0 })
  mockUseSearch.mockReset()
  mockUseSearch.mockReturnValue({})
})

// listTickets(status, limit, offset, scope, tag, category, search, priority, classification)
const lastCall = () => mockListTickets.mock.calls[mockListTickets.mock.calls.length - 1]

describe('SupportCenter filter persistence', () => {
  it('seeds the query from the URL, so filters survive a refresh', async () => {
    mockUseSearch.mockReturnValue({
      status: 'closed',
      priority: 'high',
      classification: 'bug',
      tag: 'billing',
      q: 'refund',
    })
    render(<SupportCenter />)

    await waitFor(() => expect(mockListTickets).toHaveBeenCalled())
    const call = lastCall()
    expect(call[0]).toBe('closed')
    expect(call[4]).toBe('billing')
    expect(call[6]).toBe('refund')
    expect(call[7]).toBe('high')
    expect(call[8]).toBe('bug')
  })

  it('restores the search box text from the URL', async () => {
    mockUseSearch.mockReturnValue({ q: 'refund' })
    render(<SupportCenter />)

    await waitFor(() => expect(mockListTickets).toHaveBeenCalled())
    expect(screen.getByRole('textbox', { name: /search tickets/i })).toHaveValue('refund')
  })

  it('defaults to the open queue when the URL carries no filters', async () => {
    render(<SupportCenter />)

    await waitFor(() => expect(mockListTickets).toHaveBeenCalled())
    const call = lastCall()
    expect(call[0]).toBe('open')
    expect(call[4]).toBeUndefined()
    expect(call[6]).toBeUndefined()
  })

  it('writes a status change back to the URL', async () => {
    render(<SupportCenter />)
    await waitFor(() => expect(mockListTickets).toHaveBeenCalled())

    fireEvent.click(screen.getByRole('button', { name: 'Closed' }))

    expect(mockNavigate).toHaveBeenCalled()
    const arg = mockNavigate.mock.calls[0][0]
    expect(arg.to).toBe('/support')
    expect(arg.replace).toBe(true)
    expect(arg.search({})).toEqual({ status: 'closed' })
  })

  it('keeps the filters in the URL when a ticket is opened', async () => {
    mockUseSearch.mockReturnValue({ status: 'closed', tag: 'billing' })
    mockListTickets.mockResolvedValue({
      tickets: [{
        uuid: 't-1', ticket_number: 1, subject: 'Printer on fire', status: 'closed',
        priority: 'normal', created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(), message_count: 1,
        requester_name: 'Ada', requester_email: 'ada@example.com', tags: [],
      }],
      total: 1, limit: 50, offset: 0,
    })
    render(<SupportCenter />)

    await waitFor(() => expect(screen.getByText(/Printer on fire/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/Printer on fire/))

    const openCall = mockNavigate.mock.calls.find((c) => c[0]?.search?.({})?.ticket === 't-1')
    expect(openCall).toBeTruthy()
    // The updater must merge onto the previous search, not replace it.
    expect(openCall![0].search({ status: 'closed', tag: 'billing' }))
      .toEqual({ status: 'closed', tag: 'billing', ticket: 't-1' })
  })

  it('clears every filter in one navigation', async () => {
    mockUseSearch.mockReturnValue({ status: 'closed', tag: 'billing', q: 'refund' })
    render(<SupportCenter />)
    await waitFor(() => expect(mockListTickets).toHaveBeenCalled())

    mockNavigate.mockReset()
    // Two of these render on an empty filtered list (header + empty state);
    // both are wired to the same handler.
    fireEvent.click(screen.getAllByRole('button', { name: /clear filters/i })[0])

    expect(mockNavigate).toHaveBeenCalledTimes(1)
    expect(mockNavigate.mock.calls[0][0].search({ status: 'closed', tag: 'billing', q: 'refund', ticket: 'x' }))
      .toEqual({
        ticket: 'x',
        status: undefined,
        priority: undefined,
        classification: undefined,
        tag: undefined,
        q: undefined,
      })
  })
})
