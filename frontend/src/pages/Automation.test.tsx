import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import Automation from './Automation'

vi.mock('../components/layout/PageLayout', () => ({
  PageLayout: ({ children }: { children: ReactNode }) => <>{children}</>,
}))
vi.mock('../api/config', () => ({
  getAutomationStats: vi.fn().mockResolvedValue({
    total_workflows: 512, passive_workflows: 4, watched_folders: 2, runs_this_week: 9,
    runs_today: 1, runs_today_success: 1, runs_today_failed: 0, recent_runs: [],
  }),
}))

const listWorkflows = vi.fn()
vi.mock('../api/workflows', () => ({ listWorkflows: (...args: unknown[]) => listWorkflows(...args) }))

const wf = (i: number) => ({ id: `wf-${i}`, name: `Workflow ${i}`, description: null, num_executions: 0 })

describe('Automation dashboard workflow list', () => {
  beforeEach(() => {
    listWorkflows.mockReset()
  })

  it('shows how much of the list was returned when the server holds more', async () => {
    listWorkflows.mockResolvedValue({ items: Array.from({ length: 500 }, (_, i) => wf(i)), total: 512 })
    render(<Automation />)
    expect(await screen.findByText(/showing 500 of 512/i)).toBeTruthy()
    expect(listWorkflows).toHaveBeenCalledWith({ search: undefined, limit: 500 })
  })

  it('re-queries the server with the search text rather than filtering the page', async () => {
    listWorkflows.mockResolvedValue({ items: [wf(1), wf(2)], total: 2 })
    render(<Automation />)
    await screen.findByText('Workflow 1')
    expect(screen.queryByText(/showing/i)).toBeNull()

    listWorkflows.mockResolvedValue({ items: [wf(7)], total: 1 })
    fireEvent.change(screen.getByRole('searchbox', { name: /search workflows/i }), { target: { value: 'seven' } })
    await waitFor(() => {
      expect(listWorkflows).toHaveBeenCalledWith({ search: 'seven', limit: 500 })
    })
    expect(await screen.findByText('Workflow 7')).toBeTruthy()
    expect(screen.queryByText('Workflow 1')).toBeNull()
  })
})
