import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { AuditTab } from './AuditTab'
import type { AuditLogEntry } from '../../api/audit'

const mockQueryAuditLog = vi.fn()
const mockQueryWebSearches = vi.fn()

vi.mock('../../api/audit', () => ({
  queryAuditLog: (...args: unknown[]) => mockQueryAuditLog(...args),
  exportAuditLog: () => '#',
  queryWebSearches: (...args: unknown[]) => mockQueryWebSearches(...args),
  exportWebSearches: (params: Record<string, string>) => `/export?${new URLSearchParams(params).toString()}`,
}))

const entry: AuditLogEntry = {
  uuid: 'entry-1',
  timestamp: '2026-01-01T00:00:00Z',
  actor_user_id: 'user-1',
  actor_type: 'user',
  action: 'document.create',
  resource_type: 'document',
  resource_id: 'doc-1',
  resource_name: 'Some Doc',
  team_id: null,
  organization_id: null,
  detail: {},
  ip_address: null,
}

beforeEach(() => {
  mockQueryAuditLog.mockReset()
  mockQueryWebSearches.mockReset()
})

describe('AuditTab — success', () => {
  it('renders entries and the total count on success', async () => {
    mockQueryAuditLog.mockResolvedValue({ entries: [entry], total: 1, skip: 0, limit: 25 })
    render(<AuditTab />)
    await waitFor(() => expect(screen.getByText('Some Doc')).toBeInTheDocument())
    expect(screen.getByText('(1 entries)')).toBeInTheDocument()
  })
})

describe('AuditTab — rejected query (regression for plan 005)', () => {
  it('does not render "No entries found" or a "(0 entries)" count on a rejected query', async () => {
    mockQueryAuditLog.mockRejectedValue(new Error('boom'))
    render(<AuditTab />)
    await waitFor(() => expect(screen.getByText('Failed to load audit log')).toBeInTheDocument())
    expect(screen.queryByText('No entries found')).not.toBeInTheDocument()
    expect(screen.queryByText('(0 entries)')).not.toBeInTheDocument()
  })
})

describe('AuditTab — filters', () => {
  it('resets to the first page when a filter changes', async () => {
    mockQueryAuditLog.mockResolvedValue({
      entries: Array.from({ length: 25 }, (_, i) => ({ ...entry, uuid: `e${i}` })),
      total: 60,
      skip: 0,
      limit: 25,
    })
    render(<AuditTab />)
    await waitFor(() => expect(screen.getByText('Page 1 of 3')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(() => expect(mockQueryAuditLog).toHaveBeenLastCalledWith(
      expect.objectContaining({ skip: 25 }),
    ))
    await waitFor(() => expect(screen.getByText('Page 2 of 3')).toBeInTheDocument())

    fireEvent.change(screen.getByPlaceholderText('Filter by action…'), { target: { value: 'document.create' } })
    await waitFor(() => expect(mockQueryAuditLog).toHaveBeenLastCalledWith(
      expect.objectContaining({ skip: 0, action: 'document.create' }),
    ))
    await waitFor(() => expect(screen.getByText('Page 1 of 3')).toBeInTheDocument())
  })
})

describe('AuditTab — out-of-order responses (plan 010)', () => {
  it('renders only the latest response when an earlier request resolves after a later one', async () => {
    let resolveFirst: (value: unknown) => void = () => {}
    const firstPromise = new Promise(resolve => { resolveFirst = resolve })
    const firstPayload = {
      entries: [{ ...entry, uuid: 'first', resource_name: 'First Doc' }],
      total: 1, skip: 0, limit: 25,
    }
    const secondPayload = {
      entries: [{ ...entry, uuid: 'second', resource_name: 'Second Doc' }],
      total: 1, skip: 0, limit: 25,
    }

    // First call (triggered by mount) hangs until we resolve it manually;
    // second call (triggered by the resourceTypeFilter change below, which
    // is not debounced) resolves immediately.
    mockQueryAuditLog
      .mockImplementationOnce(() => firstPromise)
      .mockResolvedValueOnce(secondPayload)

    render(<AuditTab />)
    await waitFor(() => expect(mockQueryAuditLog).toHaveBeenCalledTimes(1))

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'document' } })
    await waitFor(() => expect(mockQueryAuditLog).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(screen.getByText('Second Doc')).toBeInTheDocument())

    // Now let the slower, superseded first request resolve.
    await act(async () => {
      resolveFirst(firstPayload)
      await Promise.resolve()
    })

    // The stale response must not have overwritten the current, correct render.
    expect(screen.getByText('Second Doc')).toBeInTheDocument()
    expect(screen.queryByText('First Doc')).not.toBeInTheDocument()
  })
})

describe('AuditTab — debounced action filter (plan 010)', () => {
  it('coalesces rapid keystrokes into a single debounced request', async () => {
    mockQueryAuditLog.mockResolvedValue({ entries: [entry], total: 1, skip: 0, limit: 25 })
    vi.useFakeTimers()
    try {
      render(<AuditTab />)
      await act(async () => { await vi.advanceTimersByTimeAsync(0) })
      expect(mockQueryAuditLog).toHaveBeenCalledTimes(1) // initial mount fetch

      const input = screen.getByPlaceholderText('Filter by action…')
      const keystrokes = ['d', 'do', 'doc', 'docu', 'docum']
      for (const v of keystrokes) {
        fireEvent.change(input, { target: { value: v } })
      }

      // Still within the debounce window — no new request yet.
      expect(mockQueryAuditLog).toHaveBeenCalledTimes(1)

      await act(async () => { await vi.advanceTimersByTimeAsync(400) })

      // One debounced request fired for all 5 keystrokes — fewer than the
      // keystroke count, not one request per keystroke.
      expect(mockQueryAuditLog).toHaveBeenCalledTimes(2)
      expect(mockQueryAuditLog.mock.calls.length).toBeLessThan(keystrokes.length)
      expect(mockQueryAuditLog).toHaveBeenLastCalledWith(
        expect.objectContaining({ action: 'docum' }),
      )
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('AuditTab — web searches', () => {
  const search = {
    id: 'w1', timestamp: '2026-10-22T15:30:00Z', feature: 'workflow', user_id: 'ra-1', team_id: 't1',
    activity_id: null, provider: 'tavily', query: 'NSF equipment threshold', result_count: 0,
    status: 'error', error: 'Web search provider returned HTTP 401.',
  }

  it('shows each search, where it came from, and the failures', async () => {
    mockQueryAuditLog.mockResolvedValue({ entries: [], total: 0, skip: 0, limit: 25 })
    mockQueryWebSearches.mockResolvedValue({
      entries: [search], total: 7, skip: 0, limit: 25,
      by_feature: { chat: 6, workflow: 1 }, by_status: { ok: 6, error: 1 },
    })
    render(<AuditTab />)
    fireEvent.click(screen.getByRole('button', { name: 'Web searches' }))

    await screen.findByText('NSF equipment threshold')
    expect(screen.getByText('(7 searches)')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Chat 6 · Workflow 1 · 1 did not return results')
    expect(within(screen.getByRole('table')).getByText('Failed')).toBeInTheDocument()
    expect(screen.getByText('Web search provider returned HTTP 401.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Web searches' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('filters by source and outcome from the first page, and exports the same filter', async () => {
    mockQueryWebSearches.mockResolvedValue({ entries: [], total: 0, skip: 0, limit: 25, by_feature: {}, by_status: {} })
    mockQueryAuditLog.mockResolvedValue({ entries: [], total: 0, skip: 0, limit: 25 })
    render(<AuditTab />)
    fireEvent.click(screen.getByRole('button', { name: 'Web searches' }))
    await screen.findByText('No web searches recorded')

    fireEvent.change(screen.getByLabelText('Filter web searches by source'), { target: { value: 'chat' } })
    fireEvent.change(screen.getByLabelText('Filter web searches by outcome'), { target: { value: 'error' } })
    await waitFor(() => expect(mockQueryWebSearches).toHaveBeenLastCalledWith({ feature: 'chat', status: 'error', skip: 0, limit: 25 }))
    expect(screen.getByRole('link', { name: /Export CSV/ })).toHaveAttribute('href', '/export?feature=chat&status=error')
  })
})
