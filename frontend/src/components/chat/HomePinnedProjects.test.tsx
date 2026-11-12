import { act, fireEvent, render, renderHook, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MAX_HOME_PINS, resetHomePinnedProjectsForTests, useHomePinnedProjects } from '../../hooks/useHomePinnedProjects'

const mocks = vi.hoisted(() => ({ navigate: vi.fn(), listProjects: vi.fn() }))
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => mocks.navigate }))
vi.mock('../../api/projects', () => ({ listProjects: mocks.listProjects }))
vi.mock('@tanstack/react-query', () => ({
  useQuery: ({ enabled }: { enabled: boolean }) => ({ data: enabled ? mocks.listProjects() : undefined }),
}))
import { HomePinnedProjects } from './HomePinnedProjects'

beforeEach(() => { localStorage.clear(); resetHomePinnedProjectsForTests(); vi.clearAllMocks() })

describe('Pinned projects on Home (#1014 item 58)', () => {
  it('renders nothing and fetches nothing until a project is pinned', () => {
    const { container } = render(<HomePinnedProjects />)
    expect(container).toBeEmptyDOMElement()
    expect(mocks.listProjects).not.toHaveBeenCalled()
  })

  it('shows pinned projects in pin order and opens one into the project scope', () => {
    mocks.listProjects.mockReturnValue([
      { uuid: 'p1', title: 'NSF CAREER 2027' },
      { uuid: 'p2', title: 'NIH R01 renewal' },
    ])
    const { result } = renderHook(() => useHomePinnedProjects())
    act(() => { result.current.togglePin('p2'); result.current.togglePin('p1') })
    render(<HomePinnedProjects />)
    const names = screen.getAllByRole('listitem').map(li => li.querySelector('strong')?.textContent)
    expect(names).toEqual(['NIH R01 renewal', 'NSF CAREER 2027'])
    fireEvent.click(screen.getByRole('button', { name: 'Open project: NSF CAREER 2027' }))
    expect(mocks.navigate.mock.lastCall![0].search.project).toBe('p1')
  })

  it('leaves out a pin the viewer can no longer list', () => {
    mocks.listProjects.mockReturnValue([{ uuid: 'p1', title: 'NSF CAREER 2027' }])
    const { result } = renderHook(() => useHomePinnedProjects())
    act(() => { result.current.togglePin('gone') })
    const { container } = render(<HomePinnedProjects />)
    expect(container).toBeEmptyDOMElement()
  })

  it('caps pins and unpins on a second toggle', () => {
    const { result } = renderHook(() => useHomePinnedProjects())
    act(() => { for (let i = 0; i < MAX_HOME_PINS; i++) result.current.togglePin(`p${i}`) })
    let accepted = true
    act(() => { accepted = result.current.togglePin('one-too-many') })
    expect(accepted).toBe(false)
    expect(result.current.pinned).toHaveLength(MAX_HOME_PINS)
    act(() => { result.current.togglePin('p0') })
    expect(result.current.isPinned('p0')).toBe(false)
    expect(JSON.parse(localStorage.getItem('vandalizer:home:pinned-projects')!)).not.toContain('p0')
  })
})
