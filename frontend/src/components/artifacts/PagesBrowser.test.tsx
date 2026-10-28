import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { PagesBrowser } from './PagesBrowser'
import { browseArtifacts, type ArtifactPageResult } from '../../api/artifacts'
import { addProjectPin } from '../../api/projects'
import { announceWorkspaceWrite } from '../../lib/chatWrites'
vi.mock('../../api/artifacts', async importOriginal => ({ ...await importOriginal<typeof import('../../api/artifacts')>(), browseArtifacts: vi.fn(), createArtifact: vi.fn() }))
vi.mock('../../api/projects', () => ({ addProjectPin: vi.fn() }))
const result = (title = 'Award report'): ArtifactPageResult => ({ items: [{ uuid: 'a1', title, latest_revision: 'r1', published_revision: null, team_id: null, can_manage: true, revisions: [] }], total: 121, page: 1, page_size: 20 })
beforeEach(() => { sessionStorage.clear(); vi.clearAllMocks(); vi.mocked(browseArtifacts).mockResolvedValue(result()) })
it('browses beyond the old 100-page cap and sends search and sort to the server', async () => {
  render(<PagesBrowser />)
  await screen.findByRole('link', { name: 'Award report' })
  for (let page = 2; page <= 6; page++) {
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(browseArtifacts).toHaveBeenLastCalledWith(expect.objectContaining({ page })))
    await screen.findByRole('link', { name: 'Award report' })
  }
  expect(screen.getByText('Page 6 of 7 · 121 pages')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Search pages'), { target: { value: 'Award (C++)' } })
  await waitFor(() => expect(browseArtifacts).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'Award (C++)', page: 1 })))
  fireEvent.change(screen.getByLabelText('Sort pages'), { target: { value: 'title' } })
  await waitFor(() => expect(browseArtifacts).toHaveBeenLastCalledWith(expect.objectContaining({ sort: 'title' })))
})
it('discards late pages from another project and supports retry', async () => {
  let finish!: (value: ArtifactPageResult) => void
  vi.mocked(browseArtifacts).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  const view = render(<PagesBrowser projectUuid="old" />)
  vi.mocked(browseArtifacts).mockRejectedValueOnce(new Error('Project unavailable'))
  view.rerender(<PagesBrowser projectUuid="new" />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Project unavailable')
  finish(result('Private old page'))
  expect(screen.queryByText('Private old page')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Retry pages' }))
  await screen.findByRole('link', { name: 'Award report' })
  expect(browseArtifacts).toHaveBeenLastCalledWith(expect.objectContaining({ project_uuid: 'new' }))
})
it('pins an accessible existing page only on an explicit action', async () => {
  render(<PagesBrowser projectUuid="p1" canManage />)
  await screen.findByRole('link', { name: 'Award report' })
  fireEvent.click(screen.getByRole('button', { name: 'Add existing page' }))
  await waitFor(() => expect(browseArtifacts).toHaveBeenLastCalledWith(expect.objectContaining({ project_uuid: undefined })))
  fireEvent.click(await screen.findByRole('button', { name: 'Add Award report to project' }))
  await waitFor(() => expect(addProjectPin).toHaveBeenCalledWith('p1', { pin_type: 'artifact', target_id: 'a1' }))
  await waitFor(() => expect(browseArtifacts).toHaveBeenLastCalledWith(expect.objectContaining({ project_uuid: 'p1' })))
})

it('restores search, sorting and pagination after returning from a page', async () => {
  sessionStorage.setItem('pages:view:all', JSON.stringify({ search: 'Award', sort: 'title', page: 3 }))
  const view = render(<PagesBrowser />)
  await screen.findByRole('link', { name: 'Award report' })
  expect(browseArtifacts).toHaveBeenLastCalledWith({ search: 'Award', sort: 'title', page: 3, project_uuid: undefined })
  view.unmount()
  render(<PagesBrowser />)
  expect(screen.getByRole('searchbox', { name: 'Search pages' })).toHaveValue('Award')
  expect(screen.getByRole('combobox', { name: 'Sort pages' })).toHaveValue('title')
  await screen.findByText('Page 3 of 7 · 121 pages')
})

it('refreshes a visible library after a workflow or transcript save', async () => {
  render(<PagesBrowser />)
  await screen.findByRole('link', { name: 'Award report' })
  vi.mocked(browseArtifacts).mockResolvedValue(result('New workflow page'))
  announceWorkspaceWrite('pages')
  expect(await screen.findByRole('link', { name: 'New workflow page' })).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Award report' })).not.toBeInTheDocument()
})

it.each([
  ['chat', 'From chat'],
  ['workflow', 'From a workflow'],
  ['editor', 'Created in Pages'],
])('shows the same %s origin for owners and team members', async (kind, label) => {
  const data = result()
  data.items[0].source = { kind, conversation_uuid: 'private-chat' }
  vi.mocked(browseArtifacts).mockResolvedValue(data)
  const owner = render(<PagesBrowser />)
  expect(await screen.findByText(label)).toBeInTheDocument()
  owner.unmount()
  vi.mocked(browseArtifacts).mockResolvedValue({ ...data, items: [{ ...data.items[0],
    can_manage: false, team_id: 'team-a', source: { kind },
  }] })
  render(<PagesBrowser />)
  expect(await screen.findByText(label)).toBeInTheDocument()
  if (kind !== 'editor') expect(screen.queryByText('Created in Pages')).not.toBeInTheDocument()
})
