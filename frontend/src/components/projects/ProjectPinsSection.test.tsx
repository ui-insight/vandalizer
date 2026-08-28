import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ProjectPinsSection } from './ProjectPinsSection'

vi.mock('@tanstack/react-router', () => ({ useNavigate: () => vi.fn() }))
vi.mock('../../api/projects', () => ({
  listProjectPins: vi.fn().mockResolvedValue([]),
  addProjectPin: vi.fn(),
  removeProjectPin: vi.fn(),
}))
vi.mock('../../hooks/useExtractions', () => ({ useSearchSets: () => ({ searchSets: [
  { uuid: 'ss-1', title: 'Budget extraction' },
  { uuid: 'ss-2', title: 'Personnel extraction' },
] }) }))
vi.mock('../../hooks/useAutomations', () => ({ useAutomations: () => ({ automations: [] }) }))
vi.mock('../../hooks/useKnowledgeBases', () => ({ useKnowledgeBases: () => ({ knowledgeBases: [] }) }))

const useWorkflows = vi.fn()
vi.mock('../../hooks/useWorkflows', () => ({ useWorkflows: (opts: unknown) => useWorkflows(opts) }))

const page = (n: number, total: number) => ({
  workflows: Array.from({ length: n }, (_, i) => ({ id: `wf-${i}`, name: `Workflow ${i}` })),
  total,
  hasMore: n < total,
})

describe('ProjectPinsSection picker', () => {
  beforeEach(() => {
    useWorkflows.mockReset()
    useWorkflows.mockReturnValue(page(500, 512))
  })

  it('says how much of the workflow set it is showing instead of cutting silently', async () => {
    render(<ProjectPinsSection projectUuid="p-1" />)
    fireEvent.click(screen.getByRole('button', { name: /pin a tool/i }))
    // 500 came back of 512 on the server; 30 chips are rendered.
    expect(await screen.findByText(/showing 30 of 512/i)).toBeTruthy()
    expect(screen.getAllByRole('button', { name: /^\+ Workflow/ })).toHaveLength(30)
  })

  it('searches workflows server-side and narrows the other lists locally', async () => {
    render(<ProjectPinsSection projectUuid="p-1" />)
    fireEvent.click(screen.getByRole('button', { name: /pin a tool/i }))
    fireEvent.change(screen.getByRole('searchbox', { name: /search tools/i }), { target: { value: 'budget' } })
    await waitFor(() => {
      expect(useWorkflows).toHaveBeenCalledWith({ search: 'budget' })
    })
    // Extractions are one list with no server search: filtered in place.
    expect(screen.getByRole('button', { name: '+ Budget extraction' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: '+ Personnel extraction' })).toBeNull()
  })

  it('does not warn when the whole set fits', async () => {
    useWorkflows.mockReturnValue(page(3, 3))
    render(<ProjectPinsSection projectUuid="p-1" />)
    fireEvent.click(screen.getByRole('button', { name: /pin a tool/i }))
    expect(await screen.findByRole('button', { name: '+ Workflow 0' })).toBeTruthy()
    expect(screen.queryByText(/showing \d+ of/i)).toBeNull()
  })
})
