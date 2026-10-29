import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { PagesBrowser } from './PagesBrowser'
import * as pages from '../../api/artifacts'
import * as projects from '../../api/projects'
import type { Project } from '../../types/project'

vi.mock('../../api/artifacts', async original => ({ ...await original<typeof pages>(), browseArtifacts: vi.fn(), renameArtifact: vi.fn(), duplicateArtifact: vi.fn(), deleteArtifact: vi.fn() }))
vi.mock('../../api/projects', () => ({ listProjects: vi.fn(), addProjectPin: vi.fn() }))
const page: pages.Artifact = { uuid: 'page1', title: 'Award dashboard', latest_revision: 'r2', published_revision: 'r1', public_token: 'public-token', team_id: null, can_manage: true,
  revisions: [{ uuid: 'r1', title: 'Original', created_at: '2026-10-01T00:00:00Z', warnings: [] }, { uuid: 'r2', title: 'Award dashboard', created_at: '2026-10-02T00:00:00Z', warnings: [] }] }
const result = (item = page): pages.ArtifactPageResult => ({ items: [item], total: 1, page: 1, page_size: 20 })
const clipboard = vi.fn()
beforeEach(() => {
  sessionStorage.clear(); vi.clearAllMocks()
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: clipboard } })
  clipboard.mockResolvedValue(undefined)
  vi.mocked(pages.browseArtifacts).mockResolvedValue(result())
  vi.mocked(pages.renameArtifact).mockResolvedValue(page)
  vi.mocked(pages.duplicateArtifact).mockResolvedValue({ ...page, uuid: 'copy1', title: 'Copy of Award dashboard', public_token: null })
  vi.mocked(pages.deleteArtifact).mockResolvedValue({ ok: true })
  vi.mocked(projects.listProjects).mockResolvedValue([])
  vi.mocked(projects.addProjectPin).mockResolvedValue({ ok: true })
})
async function menu(title = page.title) {
  fireEvent.click(await screen.findByRole('button', { name: `Actions for ${title}` }))
  return screen.getByRole('menu')
}

it('offers all card actions, with keyboard navigation, Escape and outside dismissal', async () => {
  render(<PagesBrowser />)
  const popup = await menu()
  expect(within(popup).getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Open', 'Rename', 'Duplicate', 'Share', 'Copy public link', 'Download HTML', 'Add to project', 'Delete'])
  expect(screen.getByRole('menuitem', { name: 'Open' })).toHaveAttribute('href', '/pages/page1')
  expect(screen.getByRole('menuitem', { name: 'Share' })).toHaveAttribute('href', '/pages/page1#share')
  expect(screen.getByRole('menuitem', { name: 'Download HTML' })).toHaveAttribute('href', '/api/pages/page1/revisions/r2/content?download=true')
  expect(screen.getByRole('menuitem', { name: 'Open' })).toHaveFocus()
  fireEvent.keyDown(popup, { key: 'ArrowDown' })
  expect(screen.getByRole('menuitem', { name: 'Rename' })).toHaveFocus()
  fireEvent.keyDown(popup, { key: 'End' })
  expect(screen.getByRole('menuitem', { name: 'Delete' })).toHaveFocus()
  fireEvent.keyDown(popup, { key: 'Escape' })
  expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: `Actions for ${page.title}` })).toHaveFocus()
  await menu(); fireEvent.pointerDown(document.body)
  expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  await menu(); fireEvent.scroll(window)
  expect(screen.getByRole('menu')).toBeInTheDocument()
  fireEvent.wheel(document.body)
  expect(screen.queryByRole('menu')).not.toBeInTheDocument()
})

it('renames in place and refreshes the cards without saving a version', async () => {
  render(<PagesBrowser />); await menu()
  fireEvent.click(screen.getByRole('menuitem', { name: 'Rename' }))
  fireEvent.change(screen.getByLabelText('Page name'), { target: { value: '  ' } })
  expect(screen.getByRole('button', { name: 'Save name' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Page name'), { target: { value: '  New award name  ' } })
  vi.mocked(pages.browseArtifacts).mockResolvedValue(result({ ...page, title: 'New award name' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save name' }))
  expect(await screen.findByRole('link', { name: 'New award name' })).toBeInTheDocument()
  expect(pages.renameArtifact).toHaveBeenCalledWith('page1', 'New award name')
  expect(screen.getByText('2 versions')).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('No new version was created')
})

it('keeps the rename dialog and entered name when saving fails', async () => {
  vi.mocked(pages.renameArtifact).mockRejectedValue(new Error('Access changed'))
  render(<PagesBrowser />); await menu()
  fireEvent.click(screen.getByRole('menuitem', { name: 'Rename' }))
  fireEvent.change(screen.getByLabelText('Page name'), { target: { value: 'Keep my name' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save name' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Access changed')
  expect(screen.getByLabelText('Page name')).toHaveValue('Keep my name')
})

it('keeps the duplicate request stable across a network retry and offers the new copy', async () => {
  vi.mocked(pages.duplicateArtifact).mockRejectedValueOnce(new Error('Connection lost'))
  render(<PagesBrowser />); await menu()
  fireEvent.click(screen.getByRole('menuitem', { name: 'Duplicate' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Connection lost')
  await menu(); fireEvent.click(screen.getByRole('menuitem', { name: 'Duplicate' }))
  expect(await screen.findByRole('link', { name: 'Open copy' })).toHaveAttribute('href', '/pages/copy1')
  expect(vi.mocked(pages.duplicateArtifact).mock.calls[0]).toEqual(vi.mocked(pages.duplicateArtifact).mock.calls[1])
  expect(screen.getByRole('status')).toHaveTextContent('created as a private page')
})

it.each([true, false])('copies the existing public link (main link: %s) without publishing', async main => {
  vi.mocked(pages.browseArtifacts).mockResolvedValue(result({ ...page, public_token: main ? 'public-token' : null, publications: [{ token: 'version-link', revision: 'r2', published_at: '' }] }))
  render(<PagesBrowser />); await menu()
  fireEvent.click(screen.getByRole('menuitem', { name: 'Copy public link' }))
  await waitFor(() => expect(clipboard).toHaveBeenCalledWith(`${window.location.origin}/a/${main ? 'public-token' : 'version-link'}`))
  expect(await screen.findByRole('status')).toHaveTextContent(`Public link for version ${main ? 1 : 2} copied`)
})

it('offers only editable projects and adds a reference without sharing the page', async () => {
  vi.mocked(projects.listProjects).mockResolvedValue([{ uuid: 'p1', title: 'My award', role: 'owner' }, { uuid: 'p2', title: 'Shared award', role: 'editor' }, { uuid: 'p3', title: 'Read only', role: 'viewer' }] as Project[])
  render(<PagesBrowser />); await menu()
  fireEvent.click(screen.getByRole('menuitem', { name: 'Add to project' }))
  expect(await screen.findByRole('option', { name: 'My award' })).toBeInTheDocument()
  expect(screen.queryByRole('option', { name: 'Read only' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Add page' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Project'), { target: { value: 'p2' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add page' }))
  await waitFor(() => expect(projects.addProjectPin).toHaveBeenCalledWith('p2', { pin_type: 'artifact', target_id: 'page1' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Page added to project')
})

it('shows an empty project picker without allowing a submit', async () => {
  render(<PagesBrowser />); await menu()
  fireEvent.click(screen.getByRole('menuitem', { name: 'Add to project' }))
  expect(await screen.findByText('No projects you can edit are available.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Add page' })).toBeDisabled()
})

it('uses the existing delete confirmation and only removes a card after success', async () => {
  render(<PagesBrowser />); await menu()
  fireEvent.click(screen.getByRole('menuitem', { name: 'Delete' }))
  expect(screen.getByRole('dialog')).toHaveTextContent('deletes every saved version')
  fireEvent.click(screen.getByRole('button', { name: 'Keep page' }))
  expect(pages.deleteArtifact).not.toHaveBeenCalled()
  await menu(); fireEvent.click(screen.getByRole('menuitem', { name: 'Delete' }))
  vi.mocked(pages.deleteArtifact).mockRejectedValueOnce(new Error('Could not delete'))
  fireEvent.click(screen.getByRole('button', { name: 'Delete permanently' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not delete')
  expect(screen.getByRole('link', { name: 'Award dashboard' })).toBeInTheDocument()
  vi.mocked(pages.browseArtifacts).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
  fireEvent.click(screen.getByRole('button', { name: 'Delete permanently' }))
  expect(await screen.findByText('Page deleted.')).toBeInTheDocument()
  await waitFor(() => expect(screen.queryByRole('link', { name: 'Award dashboard' })).not.toBeInTheDocument())
})

it('hides owner-only actions from team readers but permits copying their accessible version', async () => {
  vi.mocked(pages.browseArtifacts).mockResolvedValue(result({ ...page, can_manage: false, public_token: undefined, latest_revision: 'r1', revisions: [page.revisions[0]] }))
  render(<PagesBrowser />); await menu()
  expect(screen.getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Open', 'Duplicate', 'Download HTML', 'Add to project'])
  expect(screen.getByRole('menuitem', { name: 'Download HTML' })).toHaveAttribute('href', '/api/pages/page1/revisions/r1/content?download=true')
})
