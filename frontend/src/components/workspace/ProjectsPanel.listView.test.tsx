/**
 * Support ticket: the Projects list had no search, stage filter or sort, so
 * finding the awarded projects among dozens meant scrolling the whole list.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Project, ProjectState } from '../../types/project'
import { applyProjectListView, countByStage } from '../projects/projectListView'

const project = (title: string, state: ProjectState, updated: string, extra: Partial<Project> = {}): Project => ({
  uuid: title.toLowerCase().replace(/\W+/g, '-'),
  title,
  description: null,
  owner_user_id: 'u1',
  team_id: null,
  state,
  root_folder_uuid: 'f',
  kb_uuid: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: updated,
  ...extra,
})

const PROJECTS = [
  project('NSF CAREER', 'active', '2026-10-10T00:00:00Z', { created_at: '2026-03-01T00:00:00Z' }),
  project('USDA Hatch', 'awarded', '2026-10-15T00:00:00Z', { created_at: '2026-02-01T00:00:00Z', description: 'Agriculture formula funds' }),
  project('NIH R01', 'draft', '2026-09-01T00:00:00Z', { created_at: '2026-05-01T00:00:00Z' }),
  project('DOE Early Career', 'awarded', '2026-08-01T00:00:00Z', { created_at: '2026-01-01T00:00:00Z' }),
]

const titles = (ps: Project[]) => ps.map(p => p.title)

describe('applyProjectListView', () => {
  const view = { query: '', stage: 'all' as const, sort: 'updated' as const }

  it('sorts by most recently updated by default', () => {
    expect(titles(applyProjectListView(PROJECTS, view))).toEqual(['USDA Hatch', 'NSF CAREER', 'NIH R01', 'DOE Early Career'])
  })

  it('sorts by creation date, name and lifecycle stage', () => {
    expect(titles(applyProjectListView(PROJECTS, { ...view, sort: 'created' }))).toEqual(['NIH R01', 'NSF CAREER', 'USDA Hatch', 'DOE Early Career'])
    expect(titles(applyProjectListView(PROJECTS, { ...view, sort: 'name' }))).toEqual(['DOE Early Career', 'NIH R01', 'NSF CAREER', 'USDA Hatch'])
    expect(titles(applyProjectListView(PROJECTS, { ...view, sort: 'stage' }))).toEqual(['NIH R01', 'NSF CAREER', 'USDA Hatch', 'DOE Early Career'])
  })

  it('searches title and description, ignoring case', () => {
    expect(titles(applyProjectListView(PROJECTS, { ...view, query: 'nsf' }))).toEqual(['NSF CAREER'])
    expect(titles(applyProjectListView(PROJECTS, { ...view, query: '  agriculture ' }))).toEqual(['USDA Hatch'])
  })

  it('filters by stage, combined with search', () => {
    expect(titles(applyProjectListView(PROJECTS, { ...view, stage: 'awarded' }))).toEqual(['USDA Hatch', 'DOE Early Career'])
    expect(titles(applyProjectListView(PROJECTS, { ...view, stage: 'awarded', query: 'doe' }))).toEqual(['DOE Early Career'])
  })

  it('counts every stage', () => {
    expect(countByStage(PROJECTS)).toEqual({ draft: 1, active: 1, submitted: 0, awarded: 2, closeout: 0, archived: 0 })
  })
})

vi.mock('@tanstack/react-router', () => ({ useNavigate: () => vi.fn() }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../projects/ProjectSummaryStats', () => ({ ProjectSummaryStats: () => null }))
vi.mock('../projects/ProjectsExplainer', () => ({ ProjectsExplainer: () => <div>explainer</div> }))
const useProjectsMock = vi.fn()
vi.mock('../../hooks/useProjects', () => ({ useProjects: () => useProjectsMock() }))

import { ProjectsPanel } from './ProjectsPanel'

// The cards, not their "Actions for project: …" menu buttons.
const cardTitles = () => screen.getAllByRole('button', { name: /CAREER|Hatch|R01|Early/ })
  .filter(b => !b.getAttribute('aria-label'))
  .map(b => within(b).getByText(/CAREER|Hatch|R01|Early/).textContent)

describe('ProjectsPanel', () => {
  beforeEach(() => {
    useProjectsMock.mockReturnValue({ projects: PROJECTS, loading: false, error: null, refresh: vi.fn(), create: vi.fn(), duplicate: vi.fn() })
  })

  it('filters by stage with counts, and offers only stages that have projects', () => {
    render(<ProjectsPanel />)
    const stages = screen.getByRole('group', { name: 'Filter by stage' })
    expect(within(stages).getAllByRole('button').map(b => b.textContent)).toEqual(['all4', 'draft1', 'active1', 'awarded2'])

    fireEvent.click(within(stages).getByRole('button', { name: /awarded/ }))

    expect(cardTitles()).toEqual(['USDA Hatch', 'DOE Early Career'])
    expect(screen.getByText('2 of 4 projects')).toBeInTheDocument()
  })

  it('searches and sorts', () => {
    render(<ProjectsPanel />)
    fireEvent.change(screen.getByLabelText('Sort projects'), { target: { value: 'name' } })
    expect(cardTitles()).toEqual(['DOE Early Career', 'NIH R01', 'NSF CAREER', 'USDA Hatch'])

    fireEvent.change(screen.getByLabelText('Search projects'), { target: { value: 'career' } })
    expect(cardTitles()).toEqual(['DOE Early Career', 'NSF CAREER'])
  })

  it('says nothing matched and clears the filters', () => {
    render(<ProjectsPanel />)
    fireEvent.change(screen.getByLabelText('Search projects'), { target: { value: 'zzz' } })
    expect(screen.getByText(/No projects match “zzz”/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))

    expect(cardTitles()).toHaveLength(4)
  })

  it('shows no toolbar before there are any projects', () => {
    useProjectsMock.mockReturnValue({ projects: [], loading: false, error: null, refresh: vi.fn(), create: vi.fn(), duplicate: vi.fn() })
    render(<ProjectsPanel />)
    expect(screen.queryByLabelText('Search projects')).not.toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Filter by stage' })).not.toBeInTheDocument()
    expect(screen.getByText('Bring your work together')).toBeInTheDocument()
  })
})
